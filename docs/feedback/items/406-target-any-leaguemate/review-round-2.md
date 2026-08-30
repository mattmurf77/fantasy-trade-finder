# Critique — FB-406, Phase 1 round 2 (Planner-as-critic)

**Date:** 2026-08-30 · **Reviewed:** prd.md, scope.md, reconciliation-log.md
**Tree:** post-FB-407, `8f722676` — every claim below re-verified against this tree,
not against round-1 reads.

**Verdict: 3 BLOCKING, 6 NON-BLOCKING.** The core design is right and the backend
story checks out end-to-end. All three blockers are spec/test-plan fixes, not
design reversals — none requires touching the arbitrations.

---

## Rulings on the Author's four flagged items

### 1. `partnerChosen` mirror vs consolidation — **ACCEPT the mirror** (with N-1 tightening)

Verified: `opponentChosenRef.current = true` appears at exactly two sites
(`InLeagueCalculator.tsx:1074` stacked chip, `:1485` merged sheet row), both
commented, and the FB-407 payload gate reads the ref at `:1230`. Promoting the
ref to state would rewrite FB-407's day-old pins for zero user-visible gain;
reading a ref during render works today only by the co-located-setState accident
and is the right thing to refuse. The adjacency pin (A-11) **is enforceable** as
count-equality + line-proximity over source text — but as specced it has two
holes, see N-1. With those closed, the mirror is drift-proof against every
plausible careless edit except a *conditionally-wrapped* adjacent pair (adjacency
and count both pass if someone wraps one line in an `if`); that residual is
acceptable and worth one honest sentence in the PRD.

### 2. Stale-verdict leak — **CONFIRMED REAL; the gated-`ev` fix is right and complete**

Verified against the tree:

- `placeholderData: (prev) => prev` — `InLeagueCalculator.tsx:616`. With
  `partnerAny` ⇒ `opponentId` null ⇒ `evalQ` disabled on a *new* key, and the
  function-form placeholder hands the previous observation's data across the key
  change. `evalQ.data` stays truthy.
- Raw reads: `git grep` shows **exactly three** `evalQ.data` occurrences — the
  `const ev = evalQ.data` derivation (`:624`) and the LeagueVerdict block
  (`:1356`, `:1358`). Eveners (`:1306`), pickerSuggestions (`:634` region), and
  the balance plan all hang off `ev`; the balance query is separately gated
  `!!opponentId` (`:707`); `SendInSleeperButton` is gated `bothSides && opponentId`
  (`:1335`). So gating `:624` (`const ev = opponentId ? evalQ.data : undefined`)
  plus re-pointing `:1356`/`:1358` at `ev` closes **every** leak path, after
  which `evalQ.data` appears exactly once in the file. `:1363`'s
  `evalQ.isLoading` is safe as-is (a disabled query is never loading), and
  `stale={evalQ.isFetching}` is inert. Endorsed. Tighten A-7's wording per N-2.

### 3. NB-1 — **REJECT AS WRITTEN** (blocking B-1; the *acceptance* survives, the trace does not)

Display-reversion after a remount is acceptable for polish scope — no argument
there, and no `TradesScreen` thread-through is warranted. But NB-1's trace models
a UI this build will not run. See B-1.

### 4. Missing explicit-Anyone analytics — **ACCEPT THE WAIVER**

`has_partner: false` stays exactly true ("the payload carried no partner") for
both unscoped states; distinguishing them is *measurement*, not honesty. A
`partner_scope` property is an analytics-taxonomy change — bright line — and
adding it would reclass this item off the polish path. scope.md §1 states the
limitation plainly and routes the decision to the operator; that is the correct
disposition. Do **not** spec it silently; if the orchestrator concludes adoption
measurement is wanted, mark it BLOCKING-ON-OPERATOR then.

---

## BLOCKING objections

### B-1 — NB-1 and TestFlight E-4 are written against the wrong runtime configuration; step 4 is unexecutable

`calc.canvas_results` is **LIT** (`config/features.json`), so on the shipping
host every successful search enters a **browse session**: the seeding effect
(`TradesScreen.tsx:5810-5823`) sets
`canvasPrefill({opponentId: rawTopCard.opponent_user_id, …})` and bumps
`prefillSeq` — `TradeBuildCanvas` increments `canvasKey` (`TradeBuildCanvas.tsx:147`)
and the calculator **remounts seeded with the browsed idea's counterparty**,
`partnerLocked` (`TradesScreen.tsx:5588`, `:7456`). Consequences:

1. **NB-1's counter-claim is false.** "When no scoped search preceded … the key
   never changes and Anyone survives the search" — wrong: the seeding effect
   changes the key on *every* successful search regardless of prior scope. The
   "Anyone" display is pre-search-only by construction; post-search the canvas
   *is* the browsed idea (which is honest — that trade has a concrete partner,
   and `initialOpponentId` set ⇒ `partnerChosen` init true ⇒ R-4 note correctly
   hidden). Session-end paths land honest-default-unchosen with the note visible
   (`Clear` seeds `{give:[],receive:[]}` with no opponentId, `:5659`; `Change`
   restores the anchor build, `:5676`; both fall back to
   `opponentUserId = scopedOpponent`, null after an Anyone search).
2. **E-4 step 4 cannot be executed as written.** After step 3's search the Team
   dropdown is dimmed/inert (`partnerLocked`) — the operator cannot "reopen the
   Team sheet and tap Any league mate" from that state without first ending the
   session, and ending it (Clear) also empties the canvas, destroying the
   verdict the step needs on screen. The stale-verdict scenario is still real
   and reachable — but only **pre-search**: pick a partner, add a give player
   (verdict + eveners render from the one-sided evaluate), then Team sheet →
   Anyone. Rewrite the step on that route.
3. **Steps 2 and 5 describe "result cards" below the canvas** — on this host
   the deck tree does not render at all (screens/CLAUDE.md, #402
   canvas-results); ideas present one at a time inside the canvas behind the
   `trades.canvas-results.pager`. The multi-counterparty check is done by
   *paging* and reading each seeded idea's partner. As written, the operator
   will be looking for UI that does not exist.

**Required:** rewrite NB-1 around the browse session (the honesty conclusion
survives; the narrow no-session remount trace applies only to the zero-results
case), rewrite E-4 steps 2/4/5 against the pager/anchor-receipt UI, and extend
code-walk hop 11 to trace the seeding effect (`:5810-5823`), not just the key
expression.

### B-2 — A-10 asserts token presence, not predicate shape; a one-character sabotage passes it while destroying the OQ-1 mandate

A-10 requires the note's condition to "reference all three of `partnerAny`,
`partnerChosen`, `receiveIds.length`". The sabotage
`partnerAny && (!partnerChosen && receiveIds.length === 0)` (`||` → `&&`)
contains all three tokens, **passes A-10**, and silently removes the scope-truth
note from the post-#407 untouched default — the exact honesty the OQ-1
arbitration mandated, on the state that actually ships to every fresh canvas.
The named S-10 flips the assertion, but the assertion is weaker than the R-4
contract it exists to pin (the note-⇔-null-payload equivalence).

**Required:** pin the exact predicate text —
`partnerAny || (!partnerChosen && receiveIds.length === 0)` — (whitespace-
normalized), not token presence. The R-4 equivalence recomputation itself checks
out on every reachable state (including the transient Anyone-tap frame before
the partner-change effect clears `receiveIds`: `partnerAny` short-circuits the
note visible while `opponent === null` nulls the payload — consistent).

### B-3 — Nothing pins `setPartnerAny(false)` on the member-row tap; the un-guarded failure is a full honesty inversion

R-2/R-8 require a member tap to reset `partnerAny`, but no E-1 assertion checks
it — A-2 pins only the Anyone row's three calls. A builder (or a later PR) that
omits the reset on the merged sheet row (`:1483-1488`) ships: Anyone → member
tap → `partnerAny` still true, `opponentId` set, `opponentChosenRef` true ⇒
**payload scoped** while the dropdown reads "Anyone" (R-3 branches on
`partnerAny` first) and the scope note renders (`partnerAny ||` short-circuit) —
the UI claims league-wide, the wire targets one team. Worse than the bug this
item fixes, and every current assertion stays green.

**Required:** new assertion (A-13): the merged team-sheet member-row onPress body
contains all four of `setPartnerAny(false)`, `opponentChosenRef.current = true`,
`setPartnerChosen(true)`, `setOpponentId(o.user_id)`; named sabotage
S-13 "sticky-anyone": drop `setPartnerAny(false)` from the member row. (The
stacked chip row needs no reset — Anyone is unreachable there — but adding it
symmetrically is harmless if the builder prefers one shape.)

---

## NON-BLOCKING objections

### N-1 — A-11 needs a pinned proximity window and an initializer-equality check

"Within its neighboring lines" is unimplementable as written — two engineers
would pick different windows; pin it (suggest ±3 lines). And A-11 does not cover
**initializer drift**: if a future FB-407 follow-up changes
`useRef(!!initialOpponentId)` (`:351`) while the mirror keeps
`useState(!!initialOpponentId)`, the pair diverges at mount on every prefill
(note claims league-wide while the payload scopes, or vice versa) with A-11
green. Add A-11b: both declarations contain the identical initializer text
`(!!initialOpponentId)`.

### N-2 — A-7's exclusion clause is ambiguous; use an occurrence count

"`evalQ.data` appears only in that derivation (plus `isLoading`/query-object
references — assert no *render* expression reads it)" — a text scan cannot
classify "render expressions", and two implementations would differ. After the
R-7 fix the correct pin is simply: **exactly one occurrence of the string
`evalQ.data` in the file** (the gated `ev` derivation). `evalQ.isLoading` /
`evalQ.isFetching` are different strings and need no carve-out.

### N-3 — scope.md §5 and PRD success-criterion 2 claim CI runs the `check-*.js` suites; it does not

Root `CLAUDE.md` §Stack: the structural suites are `npm run`-only and **gate
nothing in CI** (open NEXT.md item); CI runs `pytest`, bare `tsc --noEmit`, and
testid-lint. The claim "(tsc --noEmit, which also runs the check-*.js suites)"
is false and inflates the enforcement story — every drift-proofing claim in this
PRD binds only when someone runs the suite. Fix the wording and make the build
agent run the full `mobile/tests` set explicitly pre-push (as the ledger entry
already implies).

### N-4 — Unknown-`initialOpponentId` edge: note hidden on an unscoped search

A prefill naming a departed member (#202 fallback, `:588-590`): `partnerChosen`
initializes true but `opponent` never resolves ⇒ payload null (unscoped search)
with the note hidden — a silent league-wide search. Rare and prefill-only
(idea prefills name live counterparties); adding an `!opponent` term would flash
the note during the pre-resolve frame of every legitimate prefill, which is
worse. Document it in R-4 as a known one-sided edge; no code change.

### N-5 — R-6 interaction seam: the redirected Add drops the user's intent

Add player (receive) under Anyone → team sheet → member tap closes the sheet
scoped — but the receive picker the user originally asked for does not open;
they must tap Add again. Acceptable for polish (auto-opening the picker after a
sheet-mediated scope change is new choreography); state it in R-6 so the
TestFlight runner doesn't file it as a bug.

### N-6 — A-8's sentinel grep is best-effort; say so

A sabotage using a different sentinel string (`'*'`, `'ALL'`) escapes the named
patterns. The real guards are `tsc` (the `canvasSearch.ts` union has no string
member) and A-6/A-7's `opponentId`-gating; A-8 is a belt against the *specific*
tempting shape. One sentence in E-1 so nobody later trusts it for more than that.

---

## Arbitration attacks (standing hunt c) — all three UPHELD

- **OQ-1 (keep first-opponent display default):** upheld. The evaluate UX
  genuinely needs a roster (`oppPoolPlayers`, `:595-600`), the untouched default
  already searches league-wide post-#407, and R-4 makes it visible. Residual
  tension — the receive column names `@first`'s roster while the note says
  "searches all teams" — is FB-407's own materially-with-them rule (adding
  their players *is* choosing them, `:1223-1229` comment) and reads coherently.
- **OQ-2 (hint-only receive side):** upheld — the league-wide pool with owner
  auto-resolve is a second feature; correctly deferred.
- **OQ-3 (deck sheet out of scope):** upheld — tap-again-to-clear exists
  (`TradesScreen.tsx:8648`); an explicit row there is discoverability, not
  capability.

## Worked-example recomputation (standing hunt b) — results

- R-2's payload recompute: **correct** (opponent null nulls the payload
  regardless of the receive-clear effect's timing).
- R-4's note-⇔-payload equivalence: **correct** on all reachable states given
  `partnerChosen ≡ opponentChosenRef.current` (A-11) — except the N-4 edge, and
  contingent on B-2's exact-text pin actually enforcing the shape.
- NB-1's trace: **incorrect in the shipping config** — see B-1.
- E-1 sabotage audit: A-1…A-9, A-12 mappings sound (each named sabotage flips
  its assertion; none self-satisfies); A-10 fails the audit (B-2); A-11 passes
  with the N-1 holes noted; coverage gap at the member row (B-3).

## Invariants & Chalkline

No cross-client-invariants exposure: the wire form is *absence* of
`opponent_user_id`; no enum, color, or threshold moves; the client does not
branch on fair-packages `reason` strings. Chalkline: chalk-dim hints, ice-only
active state, no icons/emoji, static-literal testIDs — all compliant as specced.

---

# Round 3 — targeted verification (2026-08-30, same critic)

**Scope per the coordinator: incorporation spot-check + attack on the new R-10
material only. Verdict: NOT sign-off — 2 BLOCKING items (B-4, B-5), both
spec-text fixes; no design reversal.**

## Incorporation faithfulness — CONFIRMED

- **B-2 →** A-10 now pins the exact predicate
  `partnerAny || (!partnerChosen && receiveIds.length === 0)`
  (whitespace-normalized) with **both** S-10a (anyone-only) and S-10b
  (conjunction-flip) required red. Fixed as dispositioned.
- **B-3 →** A-13 pins all four member-row onPress calls with S-13
  sticky-anyone; the round-1 "member rows byte-identical" over-claim was
  corrected honestly (and `check-calc-partner-labels.js` verified label-only,
  so it stays green).
- **B-1 →** NB-1, E-4, and hops 11–13 rewritten against the LIT browse
  runtime; the key-remount trace correctly narrowed to the zero-results case.
- **N-1…N-6 →** all landed: A-11 ±3-line window + A-11b initializer equality
  (S-11b), A-7 exactly-once occurrence pin, N-3's false CI claim removed from
  scope.md §3/§5 and the success criteria, N-4 documented in R-4 with the
  safe-direction argument, N-5 folded into R-6 and E-4 step 2, A-8 marked
  best-effort with the real guards named.

## New-material verification (R-10, A-14/A-15, E-4, hops 11-13)

**R-10 mechanics check out against the code.** All prefill write sites
enumerated and correctly classified: the seeding effect (`TradesScreen.tsx:5815`)
is the only auto site; `loadCanvasPrefill` (`:3183`, reached from `:915`
route-params and `:1667` asset-idea taps), `loadSuggestion`
(`TradeBuildCanvas.tsx:154-162`), and the blank/anchor restores
(`:5659`, `:5676` — no `opponentId` at all) are tap/neutral. The `:5654-5657`
restart comment reads exactly as quoted. `CanvasPrefill` is consumed only by
`TradeBuildCanvas` + `TradesScreen` (`:76` import; MatchesScreen passes a route
param that flows through `loadCanvasPrefill` — correctly *chosen*), so the
optional field has zero interface ripple; declared diffs verified —
`TradesScreen.tsx` one line, `TradeBuildCanvas.tsx` exactly type field + prop
pass, matching the success criteria's wording.

**Design-intent recompute (the coordinator's two-sided question):**
*server-emitted* ideas are always two-sided — the fair sweep emits receive sets
of 1–3 (`trade_service.py:5849-5857`; the give anchor is non-empty by `:5758`),
and model cards are engine trades; pick-only ideas still carry the pick as a
receive asset. So against the actual gate
(`InLeagueCalculator.tsx:1230`) the receive clause does keep every intact
browsed idea scoped, with or without the ref — the argument holds. **But the
seeded prefill is not always the raw idea:** the seeding effect replays the
*edited snapshot* when one exists (`TradesScreen.tsx:5813, :5817-5818`), and
`handleBrowseSidesChange` (`:5732-5738`) snapshots whatever the user left —
including `receive: []`. A seeded mount CAN therefore carry an empty receive
side (edit the fronted idea to give-only → page away → page back). Under R-10
that state searches league-wide with the note rendering mid-session — i.e. it
degrades to R-10's own documented Clear corner (honest, note tells the wire
truth), just reached without Clear. Behavior fine; the PRD's supporting claim
overreaches — see B-5.

**A-14/A-15 sabotage audit — sound, not self-satisfying.** Both read production
text; S-14 flips A-14 in both directions (unmark the seed / mark a tap site),
S-15 flips A-15 and A-11b together. Noted, immaterial: `loadSuggestion`'s local
`setPrefill` is outside A-14's grep surface, but that rail renders only on the
experiment host where `onFindATrade` is undefined — chosen-ness cannot reach a
payload there.

**E-4 (7 steps) — every step executable against the LIT runtime.** Step 4's
stale-verdict check correctly moved pre-session; step 5's session-end lands
blank-canvas + note (verified `:5659`/`:5676` restore no `opponentId`, and
`scopedOpponent` is null after an Anyone search so nothing pins back); step 6's
discriminator is sharp — Clear-after-browse forks to the *model* path (empty
canvas), where the `trades.canvas-results.streaming` progress row actually
renders (`TradesScreen.tsx:7410-7413`), so "…/1 vs …/N opponents" is readable
exactly where the step looks. Hops 11–13 match the cited code.

## BLOCKING (round 3)

### B-4 — R-10's initializer edit turns FB-407's shipped guard RED, and the PRD does not declare the guard update

`mobile/tests/check-calc-merged-behavior.js:417-419` (assertion **20a**) pins the
declaration **verbatim**:
`/const opponentChosenRef = useRef\(!!initialOpponentId\);/` — with the rationale
"every source of initialOpponentId is deliberate", which is precisely the premise
R-10 revises. The build's `useRef(!!initialOpponentId && !seededPrefill)` makes
20a red, yet R-9 and the success criteria require all existing suites green, the
guardrails claim the pins stay "byte-identical apart from the R-10 initializer
term", and neither the file-ownership set nor any requirement names
`check-calc-merged-behavior.js` as an edited file. As specced, the build agent
hits a red gate and must improvise. **Required:** declare the 20a re-spec
explicitly (new regex matching the R-10 initializer; rationale updated to "…
deliberate, *except the browse-session seed, which arrives with
`seededPrefill`*"), add the suite file to the ownership/diff list, and state
that 20b/20b-bis/20c/20c-bis/20d need no edits — verified here: the default
effect gains only `!partnerAny` (no ref text near it, 20b-bis safe), the member
rows keep exactly two `setOpponentId(o.user_id)` sites (20c), and 20c-bis's
200-char pairing window survives the two added lines **provided the builder
keeps the ref write within ~200 chars before the `setOpponentId` call** — worth
one line in R-1/A-13 so an innocent ordering choice doesn't trip it.

### B-5 — R-4's browse-state bullet contradicts R-10/NB-1, and R-10's two-sided claim overreaches for edited seeds

R-4 still reads: "a `partnerLocked` mount always arrives via prefill …
`initialOpponentId` set ⇒ `partnerChosen` initializes **true** ⇒ note hidden. No
extra term needed by construction." Under R-10 a seeded mount initializes the
pair **false** — the note is hidden by the *receive term* (intact ideas are
two-sided), exactly as NB-1 now correctly states. Two engineers reading R-4 vs
R-10/NB-1 build to different initializer semantics. And per the recompute above,
R-10's "fair and model ideas are always two-sided" is false for the
edited-snapshot reseed (`receive: []` possible), where the note *does* render
mid-session — the accepted Clear corner reached another way. **Required:**
rewrite the R-4 browse-state bullet to the receive-term reasoning, and qualify
R-10's two-sided sentence with the edited-reseed vector, folding that state into
the already-accepted corner. No mechanics change.

## Non-findings

The remaining new material stands: no cross-client or Chalkline exposure in
R-10 (a boolean prop and one marker field, never on the wire), no analytics
delta (`has_partner` semantics untouched by the seed marker), and the
407-QA-B-1 routing itself is legitimately in scope via the orchestrator's
declared channel.
