# PRD — FB-406: "Any league mate" partner scope on the merged calculator

**Date:** 2026-08-30 · **Author:** Author agent (polish path), from [plan-g406.md](plan-g406.md)
**Reporter:** jonbonjourvi, screen `TradesHome`, v1.16.10 — *"Let you select any league mate as well as individual ones. So that it shows you all options for the player you're trying to move."*
**Class:** POLISH (planner verdict, [plan-g406.md](plan-g406.md) §4) · **Serialized behind #407** — this PRD's baseline is the post-#407 tree.
**Arbitrations honored:** OQ-1 (keep first-opponent display default; UI must not lie about league-wide search), OQ-2 (receive side = hint only), OQ-3 (deck targeting sheet out of scope). Logged in [reconciliation-log.md](reconciliation-log.md).
**Round 3 (final):** incorporates the critic's [review-round-2.md](review-round-2.md) — B-1 (browse-session runtime rewrite of NB-1 / E-4 / hop 11), B-2 (exact-predicate pin on A-10), B-3 (new A-13 sticky-anyone guard) and N-1…N-6 — plus **R-10**, the FB-407 QA-B-1 seed-prefill fix routed here by the orchestrator (`../407-finder-forced-team/mini-prd.md` §Known limitation). Dispositions in the reconciliation log, Round 3.

## The decision, in plain words

The merged Trades landing's calculator can only ever point at one leaguemate at a
time. After #407, an *untouched* canvas already searches the whole league — but the
moment a user picks a team, every future Find a Trade is scoped to it with **no way
back**: the picker sheet lists only individual members, and the partner id can never
return to empty. This change adds one explicit "Any league mate" row to that sheet
(backed by a real unscoped state), makes the Team dropdown honest about what the
search will do in every state, and puts a one-line hint on the receive side instead
of building a league-wide receive picker. It also closes a hole FB-407's QA found
(R-10): after a search loads results into the canvas, tapping Clear and searching
again silently targeted the loaded idea's team — now an emptied canvas always
restarts league-wide. Client-only; the backend's league-wide sweep already ships,
is documented, and is tested.

## Baseline (post-#407, verified in this tree at d2a0b0bb + FB-407 working-tree build)

All anchors below are cited as **stable anchor + line at time of writing**; the
FB-407 build agent is editing `InLeagueCalculator.tsx` concurrently, so treat line
numbers as approximate and the named functions/testIDs/expressions as authoritative.

- `opponentChosenRef = useRef(!!initialOpponentId)` exists (`InLeagueCalculator.tsx:351`), is set `true` at exactly two user-tap sites (stacked chip row `:1074`, team-sheet row `:1485`, both commented `FB-407 — a tap IS a choice`), and gates the Find a Trade payload: `opponent: opponent && (opponentChosenRef.current || receiveIds.length > 0) ? {…} : null` (`calc.action.find-a-trade` onPress, `:1229-1231`).
- The default-to-first effect still fires whenever `opponentId` is null (`:546-548`, comment "Default to the first opponent once the list loads") — post-#407 it scopes nothing, but it makes a *displayed* unscoped state impossible.
- The team sheet (`calc.team-sheet`, `:1462`) lists only members (`calc.team-sheet.${o.user_id}` rows, `:1477`); the dropdown (`calc.team-dropdown`, `:972`) reads `@user` or `Choose…` (`:994`) and is inert under `partnerLocked` (`:979`).
- Downstream is null-safe end to end: `forkCanvasSearch` types `opponent` nullable and reports `has_partner` (`utils/canvasSearch.ts:44-58`); `handleInlineFindATrade` adopts it via `setSheetOpponent(fork.opponent)` (`TradesScreen.tsx:3055`); `scopedOpponent` derives to `undefined` (`:832-836`); the fair path spreads `opponent_user_id` only when set (`runFairPackages`, `:3353`) and the model path sends `undefined` (`generateMutation`, `:1850`). Server: omitted `opponent_user_id` ⇒ every-leaguemate sweep (`backend/server.py:12398-12399`/`:12460` → `backend/trade_service.py:5797-5803`), each idea carrying its own `counterparty_user_id`/`counterparty_username` (`:5816-5817`); covered by `backend/tests/test_fair_packages.py:15`/`:203` and documented in `docs/api-reference.md` (fair-packages row: *"or from every league-mate's when no partner is named"*).

**The residual gap this PRD closes:** post-#407 the unscoped run exists only as the
*default* — it is invisible (dropdown shows a manager the user never picked, with
nothing saying the search is league-wide) and **irreversible** (once
`opponentChosenRef` flips true, every later search is scoped until the canvas
remounts). #406 is the explicit, honest, reversible half.

## Requirements

### R-1 — "Any league mate" row in the merged team sheet

A leading row above the member rows inside the `calc.team-sheet` Modal:

- testID `calc.team-sheet.any` (static literal — no testid-lint allow-list entry
  needed; member rows keep their `calc.team-sheet.${o.user_id}` template ids
  untouched).
- Primary text **"Any league mate"** (same `styles.dropdownValue` text treatment as
  member handles; ice `color: ice.base` when active, matching the member rows'
  active treatment at `:1495`). Dim sub-line (chalk-dim, `body-sm` — per
  design-system.md hints are chalk-dim, never chalk-faint): **"See offers from
  every team"**. No icon, no emoji, no new colors (Chalkline).
- `accessibilityRole="button"`, `accessibilityState={{ selected: partnerAny }}`,
  `accessibilityLabel="Any league mate — see offers from every team"`.
- Tap: `haptics.selection()`, set the unscoped state (R-2), close the sheet.
- **Member rows: presentation byte-identical, onPress extended by exactly two
  writes.** The Anyone row is additive above the existing `opponents.map(…)`;
  member rows' labels, summaries, badges, testIDs and styles are untouched
  (`check-calc-partner-labels.js` pins the label/summary construction and stays
  green), but each member row's onPress gains `setPartnerAny(false)` and the R-4
  `setPartnerChosen(true)` alongside its existing calls — required by R-2/R-8
  and pinned by A-13 (critic B-3: without the reset, Anyone → member tap ships a
  UI claiming league-wide while the wire targets one team). **Ordering
  constraint (critic B-4):** every new write added at a member-row tap site must
  keep `opponentChosenRef.current = true` within FB-407's 20c-bis pairing
  window — the ~200 chars **before** the `setOpponentId(o.user_id)` call
  (`check-calc-merged-behavior.js` 20c-bis) — so an innocent ordering choice
  doesn't turn that suite red.

*Pass criteria:* structural E-1 assertions A-1/A-2; code-walk hop 1; TestFlight step 2.

### R-2 — A real unscoped state, boolean, never a sentinel

- New renderable state `const [partnerAny, setPartnerAny] = useState(false)` in
  `InLeagueCalculator`. Choosing Anyone sets `partnerAny = true` **and**
  `setOpponentId(null)`; choosing a member row sets `partnerAny = false` (plus the
  existing FB-407 `opponentChosenRef.current = true` + `setOpponentId(o.user_id)`).
- The default-to-first effect (`:546-548`) gains a `!partnerAny` guard (and
  `partnerAny` in its deps) so the unscoped state is stable — without the guard the
  effect re-selects `opponents[0]` the moment `opponentId` goes null.
- `setOpponentId(null)` deliberately rides the **existing** partner-change effect
  (`prevOpponentRef`, `:579-585`), which clears `receiveIds` and closes the picker —
  receive assets belong to the old partner's roster, and a canvas still holding them
  would re-scope the payload via the FB-407 `receiveIds.length > 0` clause.
  Recomputed against the actual gate: after the clear, `opponent === null` (find on
  a null id, `:587`) ⇒ `opponent && (…)` is falsy ⇒ payload `opponent: null`. The
  give side is kept — it is the user's own roster and the thing being shopped.
- **No sentinel id, ever**: no `'any'`-style value may be assigned to `opponentId`,
  compared against `user_id`, or placed in any request body / `api/*` call.
  `opponentChosenRef`'s two write sites are **untouched** (FB-407's guard pins
  them); this feature only adds the adjacent mirror in R-4 and the one
  initializer term in R-10.

*Pass criteria:* E-1 A-2/A-3/A-8; code-walk hops 1-4; `tsc --noEmit` clean.

### R-3 — Honest dropdown (and receive column) labels

- Team dropdown value (`:994`): three states — `partnerAny` → **"Anyone"**;
  else `opponent` → `@{username}`; else **"Choose…"** (pre-load only, exactly as
  today). a11y label gains the matching branch:
  `"Team: Anyone — offers from every team. Change team"`.
- The dropdown stays inert under `partnerLocked` (`:979`, untouched) — Anyone is
  unreachable while the host browses an idea, which comes free with the existing
  `disabled`.
- Receive column header: `TradeSide`'s `teamName` prop (currently
  `opponent ? '@user' : 'their roster'`, `:1154`) reads **"any team"** while
  `partnerAny` — "their roster" would name a team that no longer exists. One
  ternary at the call site; `TradeSide.tsx` itself is untouched.

*Pass criteria:* E-1 A-9; TestFlight step 2.

### R-4 — Scope-truth note (the OQ-1 honesty mandate)

When the search would run league-wide, the UI says so **before** the tap, in both
unscoped states (explicit Anyone *and* the post-#407 untouched default):

- One dim line directly under the `calc.action-row`, testID
  `calc.search-scope-note`, `body-sm` chalk-dim (the file's existing `styles.note`
  treatment, e.g. `:1110` — content-carrying hints are chalk-dim per
  design-system.md's contrast rule), copy:
  **"Find a Trade searches all teams — pick a team to target one."**
- Render condition (merged layout only):
  `merged && (partnerAny || (!partnerChosen && receiveIds.length === 0))` — the
  exact complement of the FB-407 payload gate, so the note is visible **iff** the
  payload's `opponent` would be `null`. Recomputed against the gate: note hidden ⇒
  `partnerChosen || receiveIds.length > 0` ⇒ (with `opponent` non-null) the payload
  carries the partner ⇒ scoped, and vice versa. The note disappearing IS the scoped
  signal; no scoped-state caption is added (the dropdown already names the team, and
  the action row's frame budget is contested — D-157).
- **`partnerChosen` mirror:** `opponentChosenRef` is a ref by FB-407 design
  ("nothing renders from it") and stays authoritative for the payload. R-4
  introduces a render need, satisfied by
  `const [partnerChosen, setPartnerChosen] = useState(…)` written
  `true` on the **adjacent line** (±3 lines, N-1) at each of the two existing
  `opponentChosenRef.current = true` sites (and set — value `true` — nowhere else;
  the Anyone tap touches neither). Its initializer is **textually identical to the
  ref's** — post-R-10 both read `!!initialOpponentId && !seededPrefill` — with the
  equality itself pinned (E-1 A-11b) so initializer drift cannot desynchronize the
  pair at mount. Adjacency + count-equality are pinned by A-11. **Honest residual**
  (critic ruling 1): a *conditionally wrapped* adjacent pair (someone wraps one of
  the two lines in an `if`) passes both pins — accepted as the price of not
  rewriting FB-407's fresh guards; no plausible careless edit takes that shape.
  This keeps FB-407's shipped code untouched apart from the R-10 initializer
  term, which FB-407's own Known-limitation section names as the intended fix
  shape — and which requires the declared 20a re-spec in R-10 (critic B-4); the
  other FB-407 pins (20b…20d) need no edits. (The consolidation alternative —
  promote the ref itself to state and rewrite the FB-407 assertions — was
  rejected by the critic; reconciliation log, Round 2 ruling 1.)
- **Known one-sided edge (N-4, documented, no code change):** a prefill naming a
  departed member (#202 fallback — `partnerCollapsed`/`opponent` never resolve,
  `:590`) initializes `partnerChosen` true while `opponent` stays null ⇒ the
  payload is null (unscoped search) with the note hidden. Rare and prefill-only —
  idea prefills name live counterparties. Adding an `!opponent` term would flash
  the note during the pre-resolve frame of every legitimate prefill, which is
  worse. The failure is one-sided in the safe direction — a league-wide search
  runs unannounced; the note never announces league-wide while the wire is
  scoped — and is accepted.
- Browse state (rewritten per critic B-5 — must read consistently with
  R-10/NB-1): a `partnerLocked` mount arrives via the browse-session **seed**
  prefill (`TradeBuildCanvas.tsx:152/171`, `initialOpponentId` set), which under
  R-10 initializes `partnerChosen`/the ref **false**. The note stays hidden on a
  seeded mount by the **receive term** of the predicate, not by chosen-ness: an
  intact server-emitted idea always carries receive assets, so
  `receiveIds.length === 0` is false. When an *edited* seed carries
  `receive: []` (see R-10's edited-reseed corner) the note **renders**
  mid-session — honestly, since that search runs league-wide. Non-seed prefills
  (idea taps, handoffs) initialize the pair true as before. No extra
  `partnerLocked` term is needed in the predicate.

*Pass criteria:* E-1 A-10/A-11; code-walk hop 4b; TestFlight steps 1, 5 and 6.

### R-5 — The unscoped run: payload and wire contract

With `partnerAny` active, Find a Trade behaves exactly as the post-#407 untouched
default — the row's value is explicitness and reversibility, not a new wire shape:

- Payload `opponent: null` on both forks (falls out of the untouched FB-407 gate,
  since `opponent` resolves to null — no new payload logic).
- Give-side assets present ⇒ fair path: `POST /api/trades/fair-packages` **without**
  `opponent_user_id` ⇒ all-members sweep, ideas carrying per-idea counterparties ⇒
  a mixed-partner deck with zero card changes. Empty canvas ⇒ model path:
  `POST /api/trades/generate` with `opponent_user_id: undefined` ⇒ the ordinary
  all-teams model deck.
- **Expected `TradesScreen.tsx` diff: R-10's one-line seed marker only** (the
  orchestrator routed the FB-407 QA-B-1 fix into this build, amending the plan §8
  zero-diff expectation through the declared channel). `handleInlineFindATrade`
  (`:3046-3073`), `runFairPackages` (`:3353`), `generateMutation` (`:1850`), and
  `utils/canvasSearch.ts` are consume-as-is. If any scoped-empty / anchor-receipt
  copy turns out to need an "Anyone" variant, the builder must flag it to the
  orchestrator **before** editing (plan §5.5) — it is the only other candidate edit.
- Analytics: **no new events, no property changes.** The existing
  `calc_find_a_trade_tapped.has_partner: false` covers the unscoped run; it cannot
  distinguish explicit-Anyone from default-unchosen (both are honestly
  `has_partner: false`) — accepted, see [scope.md](scope.md) §1.

*Pass criteria:* E-1 A-4 (payload gate intact) + A-8 (nothing sentinel-shaped in any
request); code-walk hops 5-9; existing `backend/tests/test_fair_packages.py` green
(zero backend diff); TestFlight steps 2-3.

### R-6 — Receive side under Anyone: hint only (OQ-2)

- A one-line hint in the receive column while `partnerAny`, testID
  `calc.receive-any-hint`, chalk-dim `body-sm`:
  **"Pick a team to add specific players — Find a Trade already shows offers from
  everyone."**
- The receive side's "Add player" button (`calc.league-receive-add`, `:1159`)
  **opens the team sheet** (`setTeamPickerOpen(true)`) while `partnerAny`, instead
  of `setPicker('receive')` — the pool `oppPoolPlayers` is empty by construction
  (`opponentId ? … : []`, `:595-600`), and an empty picker is a dead end. This is a
  branch in the `onAdd` callback at the call site (`:1162`); `TradeSide`'s
  interface is untouched (its `onAdd` is required, so hiding the button would be a
  component change — rejected as the larger diff). Give side unchanged.
- **No league-wide receive pool** this round — that is the deferred OQ-2
  alternative (see Out of scope).
- **Interaction seam, stated so the TestFlight runner doesn't file it (N-5):**
  the redirected flow drops the original intent by design — Add player (receive)
  under Anyone → team sheet → member tap closes the sheet *scoped*, but the
  receive picker does not then auto-open; the user taps Add again. Auto-opening
  the picker after a sheet-mediated scope change would be new choreography;
  accepted for polish scope.

*Pass criteria:* E-1 A-12; TestFlight step 2.

### R-7 — No dishonest evaluate state while unscoped

Under Anyone, nothing that means "verdict against a specific partner" may render or
fetch:

- `evalQ` never fires: its `enabled` already requires `!!opponentId` (`:613`) and
  must keep requiring a **resolved partner id** — never a sentinel, never
  `partnerAny`.
- **Placeholder retention is a real leak and must be closed:** `evalQ` uses
  `placeholderData: (prev) => prev` (`:615`), which keeps the *previous key's* data
  visible across the `opponentId` key change even while disabled. With give-side
  players on the canvas, the verdict block (`anySide && evalQ.data`, `:1356`) and
  eveners (`anySide && ev?.eveners…`, `:1306`) would render the **old partner's**
  verdict under "Anyone". Required behavior: while `opponentId` is null, all
  evaluate-derived UI is absent — verdict/consensus block, eveners / trade-options
  rows, lineup-impact line, and the picker's Suggested rows (`:634`). Suggested
  implementation (builder may refine): gate the single derivation —
  `const ev = opponentId ? evalQ.data : undefined` — and make the `:1356`/`:1363`
  block read the gated `ev` instead of raw `evalQ.data`; everything else already
  hangs off `ev`.
- The ✓ confirm cell stays disabled via the **textually untouched** expression
  `!onLikeTrade || !bothSides || !opponent || queueing` (`:1272`) — pinned by
  `check-calc-merged-behavior.js` 18-19d and the components/CLAUDE.md "anything
  broader" warning. `opponent === null` under Anyone already disables it; do not
  add a `partnerAny` term.

*Pass criteria:* E-1 A-5/A-6/A-7; code-walk hop 4; TestFlight step 4.

### R-8 — Round trip

From Anyone, tapping a member row restores today's scoped behavior byte-identically:
`partnerAny` false, `opponentChosenRef`/`partnerChosen` true, `opponentId` set ⇒
scoped sweep on the next Find a Trade, their-roster receive pool, live evaluate, ✓
eligibility — all via existing code paths. And the reverse stays available forever:
the Anyone row is always present in the sheet, so a chosen scope is now reversible
(the capability that did not exist post-#407).

*Pass criteria:* code-walk hop 10; TestFlight steps 3 and 5; E-1 A-2/A-3 (state
transitions).

### R-9 — Byte-identical everywhere else

- **Stacked (non-merged) layout:** no Anyone affordance — the stacked chip row
  (`:1060-1090`) is untouched; the team sheet renders only under `merged`
  (`:1450-1512` is inside the merged branch), and the scope note is `merged`-gated.
  The stacked page is evaluate-first with no Find a Trade row.
- **`partnerLocked` browse state:** dropdown inert (`:979`), receive-add redirect
  unreachable (requires `partnerAny`, which a prefill mount initializes false) —
  Anyone cannot be entered mid-browse.
- **Other hosts** (FeaturedTradeWindow, the pushed `TradeCalculatorScreen` page,
  the #270 experiment mount): no behavior change — they do not pass R-10's
  optional `seededPrefill` prop (defaults to today's behavior), and `partnerAny`
  is internal state that defaults off. Flag-off (`calc.merged_layout` false) is
  unreachable-by-construction.
- All existing structural suites stay green: `check-calc-merged-behavior.js`
  (**after its declared 20a re-spec** — R-10, critic B-4; its other assertions
  untouched), `check-calc-partner-labels.js`, `check-inline-home.js`,
  `check-canvas-results.js`, `check-calc-merged-layout.js`, `check-calc-tour.js`.

*Pass criteria:* full `mobile/tests` suite + `tsc --noEmit` + testid-lint green;
TestFlight step 7.

### R-10 — Seed-prefill never counts as chosen (FB-407 QA-B-1 fix, routed here)

The #402 browse-session **seeding effect** (`TradesScreen.tsx:5811-5823`) loads the
fronted idea into the canvas with **no user tap**: it writes
`setCanvasPrefill({opponentId: rawTopCard.opponent_user_id, give, receive})` and
bumps `prefillSeq`, remounting the calculator with `initialOpponentId` = that
counterparty — which initializes `opponentChosenRef` **true** for a team the user
never chose (`useRef(!!initialOpponentId)`, `InLeagueCalculator.tsx:351`).
Consequence today (FB-407 mini-prd §Known limitation): unscoped/Anyone search →
canvas action-row **Clear** (`calc.action.clear` — clears the sides *without* a
remount) → **Find a Trade** silently runs a single-team sweep of the seeded
counterparty. That is the exact silent-scope class this batch exists to kill, now
reachable *from* the Anyone flow this item ships — so the fix belongs here.

**Design-intent check (why this is a fix, not a reversal of #402):** while the
seeded idea sits on the canvas, its receive side is non-empty for every
**server-emitted** idea (the fair sweep emits receive sets of 1-3,
`trade_service.py:5849-5857`; model cards are engine trades), so the FB-407
"materially with them" clause (`receiveIds.length > 0`) scopes the search to the
browsed counterparty **with or without** the ref — in-session scoping to the
browsed idea is preserved untouched. **Edited-reseed qualification (critic
B-5):** the seeding effect replays the *edited snapshot* when one exists
(`TradesScreen.tsx:5813`, `:5817-5818`), and an edit can leave `receive: []` —
so a seeded mount CAN be give-only (edit the fronted idea to give-only → page
away → page back). Under R-10 that state searches league-wide with the R-4 note
rendering mid-session: the same already-accepted honest corner as
Clear-after-browse below, reached without Clear — **accepted behavior**, the
note tells the wire truth.
The ref only ever matters once the sides are emptied — and #402's own
pass-exhaustion comment (`TradesScreen.tsx:5654-5657`: restore the blank canvas
"so the action row's Find a Trade cell honestly reads as the restart") says an
emptied canvas's Find a Trade is a *restart*, i.e. unscoped. FB-407's DECISIONS
wording ("a partner counts as the search scope only when **chosen** — tap,
prefill, or receive-side assets") counted prefills as chosen because they are
"normally from a tapped idea/card" — the seed prefill is the one prefill that
isn't, and its Known-limitation section names this exact fix shape.

**Mechanics:**

- `CanvasPrefill` (`TradeBuildCanvas.tsx:59`) gains optional `seeded?: boolean`.
  **Only** the seeding effect's write (`TradesScreen.tsx:5815`) sets
  `seeded: true` — the tap/handoff sites (`loadCanvasPrefill` `:3183`, suggestion
  tap `loadSuggestion` `TradeBuildCanvas.tsx:154-162`, route-param arrivals
  `:915`/`:1667`) and the blank/anchor restores (`:5659`, `:5676`) do not.
- `TradeBuildCanvas` passes it through as a new optional prop:
  `seededPrefill={!!prefill?.seeded}` on the `InLeagueCalculator` mount (`:167`).
- `InLeagueCalculator` initializers become
  `useRef(!!initialOpponentId && !seededPrefill)` and the R-4 mirror
  `useState(!!initialOpponentId && !seededPrefill)` — **textually identical**
  (A-11b). Nothing else reads the prop. `partnerLocked`, the evaluate query, the
  ✓ cell, and the seeded display (`@counterparty` in the locked dropdown) are all
  unchanged — the seeded idea still evaluates and queues against its counterparty.
- Resulting behavior: mid-session Find a Trade over the intact idea → scoped
  (receive clause). Mid-session **after canvas Clear** → payload `opponent: null`
  → league-wide restart, and the R-4 note renders (`partnerChosen` false, sides
  empty) — honest, though its "pick a team" clause is weak while the dropdown is
  session-locked (the user targets by paging to an idea or ending the session);
  accepted corner, logged.
- **Declared guard re-spec (critic B-4) — `mobile/tests/check-calc-merged-behavior.js`
  joins the diff set.** The new initializer turns FB-407's shipped assertion
  **20a** red: `check-calc-merged-behavior.js:417-419` pins the old declaration
  verbatim (`/const opponentChosenRef = useRef\(!!initialOpponentId\);/`). The
  build agent updates 20a in the same commit: the pinned regex becomes the R-10
  twin-initializer declaration
  (`const opponentChosenRef = useRef(!!initialOpponentId && !seededPrefill);`),
  and its hint text becomes "every source of initialOpponentId is deliberate —
  prefill or explicit scope — *except the browse-session seed, which arrives
  with `seededPrefill`*". The assertion stays **two-sided** (still red if the
  seed negation is dropped OR the declaration drifts). **20b / 20b-bis / 20c /
  20c-bis / 20d need no edits** (verified by the critic): the default effect
  gains only `!partnerAny` — no ref text within 20b-bis's ±400-char window —
  and the member rows keep exactly two `setOpponentId(o.user_id)` sites.
- Fixes FB-407's Known limitation; its follow-up closes on this ship (note in
  `../407-finder-forced-team/status.md` at ship time — cross-item bookkeeping,
  builder task).

*Pass criteria:* E-1 A-14/A-15; code-walk hops 11-13; TestFlight step 6;
`tsc --noEmit` (the optional prop breaks no other host — FeaturedTradeWindow, the
pushed page, and the #270 mount simply omit it, defaulting to today's behavior).

## Known behavior (documented, not a defect)

**NB-1 — "Anyone" is a pre-search display; a successful search hands the canvas to
the browsed idea (rewritten per critic B-1 against the shipping
`calc.canvas_results`-LIT runtime).** On the live host every successful search
with ≥1 idea enters a **browse session**: the seeding effect
(`TradesScreen.tsx:5811-5823`) prefills the fronted idea and bumps `prefillSeq`,
so `TradeBuildCanvas` bumps `canvasKey` (`TradeBuildCanvas.tsx:145-150`) and the
calculator **remounts seeded with that idea's counterparty**, `partnerLocked`
(`TradesScreen.tsx:5588`, `:7456`). So after an Anyone search the dropdown reads
the browsed idea's manager, not "Anyone" — which is honest: the canvas now *is* a
concrete trade with a concrete partner, and (with R-10) `partnerChosen`
initializes false while the non-empty receive side keeps in-session searches
scoped to the browsed idea (intact ideas — an edited give-only reseed instead
searches league-wide with the note rendering, R-10's accepted corner). The R-4
note is correctly hidden while an intact idea's sides are on the canvas. Session-end paths land on the honest default-unchosen
state with the note visible: the pager Clear / pass-exhaustion restore a blank
prefill with no `opponentId` (`:5659`, `endBrowseSession` `:5676`), Change
restores the anchor build, and `initialOpponentId` falls back to
`scopedOpponent` — null after an Anyone search — so nothing pins back. The
narrow key-remount trace (key `…-B` → `…-none` when a scoped search preceded)
now applies **only to the zero-results case**, where no seeding occurs: there, a
fresh-session Anyone search leaves the key unchanged and the "Anyone" display
survives; after a previously *scoped* search it remounts to default-unchosen
(note visible, still league-wide). In every path the wire truth and the R-4 note
stay consistent; only the "Anyone" *label* is pre-search-only. Threading the
choice through the host to preserve the label was rejected (host diff beyond
R-10's one line, or a banned sentinel) — accepted for polish scope.

## Out of scope

- **Anyone as the default** (OQ-1): the display default stays first-opponent — the
  calculator's evaluate UX needs a roster to browse; post-#407 the untouched default
  already *searches* league-wide, and R-4 makes that visible. Orchestrator ruling.
- **League-wide receive pool** under Anyone, with owner auto-resolution (OQ-2
  alternative; FB-47-style acquire pool): a second feature — pool build, owner
  resolution, mixed-owner conflicts. Hint-only this round; candidate follow-up.
- **Deck targeting sheet "Any team" row** (OQ-3): the sheet already has
  tap-again-to-clear (`TradesScreen.tsx:8648`); an explicit row there is a
  discoverability nicety. Possible follow-up, not this item.
- **A `partner_scope` analytics property** distinguishing explicit-Anyone from
  default-unchosen: an analytics-taxonomy change is bright-line scope; only if the
  operator asks for the measurement.
- Backend, web, extension: no equivalent surface; zero diff.

## Guardrails

- **Never** a sentinel partner id in state comparisons or request bodies (E-1 A-8).
- **Never** touch the ✓ disabled expression, the FB-407 payload gate, the FB-407
  ref *write sites*, or the member-row label/summary construction — all pinned by
  existing suites. (The ref's *initializer* changes once, per R-10 — the shape
  FB-407's own Known-limitation names — and the member-row onPress gains exactly
  the two R-1 writes; nothing else in either.)
- `calc.team-sheet.any` cannot collide with a member row: platform user ids are
  numeric/opaque strings, never the literal `any`; the guard asserts the Anyone row
  renders outside the `opponents.map` loop regardless.
- Chalkline: no icons/emoji on the new row, chalk-dim for both hint lines
  (content-carrying text is never chalk-faint), ice only for the active state, no
  new tokens, 11pt floor respected (`body-sm` = 13).
- New testIDs (`calc.team-sheet.any`, `calc.search-scope-note`,
  `calc.receive-any-hint`) are static literals → `mobile/scripts/testid-lint.sh`
  green with no allow-list entries.

## Screen captures as inputs

`screens/manifest.json` (frozen 2026-08-11, D-056) has **no capture of the merged
landing this change touches**: the merged canvas, team sheet, and action row all
postdate the freeze (merged-view trim 2026-08-28, `nav.trades_landing` v1.16.11).
The nearest artifacts are `screens/mobile/calc/league-mode.png` /
`live-populated.png` (the **pre-merge stacked** calculator — shows the old partner
chip row, useful only as history) and `screens/mobile/trades/populated.png` (the
pre-merge deck landing). Stated honestly: no capture covers the surface being
extended; the TestFlight checklist is the only runtime visual evidence.

## D-056 evidence plan

### E-1 — Structural guard: `mobile/tests/check-any-partner.js` (new)

Dependency-free plain-node suite in the `check-calc-merged-behavior.js` style
(assert/read helpers, source-text pins against `mobile/src/components/InLeagueCalculator.tsx`
unless noted), plus `"test:any-partner": "node tests/check-any-partner.js"` in
`mobile/package.json`. Every behavioral assertion is listed with its **named
sabotage** — a plausible regression edit to *production* code (never to the test)
that must flip the assertion red; each was audited for self-satisfaction: none
hardcodes the expected value into the code it checks, and each sabotage is a change
a careless future PR could actually make.

| # | Assertion (against source text) | Named sabotage (must go red) |
|---|---|---|
| A-1 | `calc.team-sheet.any` testID exists **inside** the team-sheet Modal region (after the `testID="calc.team-sheet"` marker) and **outside/above** the `opponents.map(` loop | **S-1 revert-row:** delete the Anyone row, restoring the members-only sheet |
| A-2 | The `calc.team-sheet.any` onPress body contains all three of `setPartnerAny(true)`, `setOpponentId(null)`, `setTeamPickerOpen(false)` | **S-2 half-state:** drop `setOpponentId(null)` — the flag flips but the old partner keeps feeding evaluate/receive pool |
| A-3 | The default-to-first effect body (the one containing `opponents[0].user_id`) is guarded on the unscoped state (`!partnerAny` in its condition) and lists `partnerAny` in its deps | **S-3 unguarded-default:** restore `if (!opponentId && opponents.length)` — the default re-selects the moment Anyone nulls the id |
| A-4 | The find-a-trade payload's `opponent:` expression still contains the FB-407 gate `opponentChosenRef.current \|\| receiveIds.length > 0` | **S-4 pass-through:** revert to unconditional `opponent ? {…} : null` — the auto-default scopes again (also pinned in the FB-407 section of `check-calc-merged-behavior.js`; kept here as a cross-suite belt because a regressing PR can edit one suite) |
| A-5 | The ✓ cell's `disabled={!onLikeTrade \|\| !bothSides \|\| !opponent \|\| queueing}` appears **verbatim, exactly once** | **S-5 broadened-cell:** append `\|\| partnerAny` (recreates the permanently-dead control the components/CLAUDE.md warning names) or drop `!opponent` (lets a partnerless queue through) |
| A-6 | `evalQ`'s `enabled:` expression contains `!!opponentId` | **S-6 unpartnered-eval:** relax `enabled` to the sides-only condition — the query fires with a null partner (`opponentId!` = null on the wire) |
| A-7 | The evaluate data is consumed through one partner-gated derivation (`const ev =` line contains an `opponentId` gate) and — the enforceable form, per N-2 — the string `evalQ.data` occurs **exactly once** in the file (that derivation). `evalQ.isLoading`/`evalQ.isFetching` are different strings and need no carve-out | **S-7 stale-verdict:** render the verdict block from raw `evalQ.data` (restores the `placeholderData` leak: the old partner's verdict shown under "Anyone") |
| A-8 | No sentinel: the file contains no `setOpponentId('any')` / `'any'` compared to `user_id` / `opponent_user_id: 'any'`-shaped text; and `utils/canvasSearch.ts` still types `opponent` as `{userId; name} \| null` (no `'any'` union member). **Best-effort by design (N-6):** a different sentinel string (`'*'`, `'ALL'`) escapes these greps — the real guards are `tsc` (the union has no string member) and A-6/A-7's `opponentId`-gating; A-8 is a belt against the one tempting shape, and must never be trusted for more | **S-8 sentinel-swap:** implement Anyone as `setOpponentId('any')` — the sentinel reaches `evaluateTradeInLeague`'s key/args and request bodies |
| A-9 | The dropdown value expression contains a `partnerAny` branch yielding `'Anyone'`, and the dropdown `accessibilityLabel` expression contains a matching `partnerAny`/Anyone branch | **S-9 lying-label:** leave the label at `opponent ? @user : 'Choose…'` — under Anyone it claims nothing is selected |
| A-10 | `calc.search-scope-note` exists; its render condition contains the **exact predicate text** `partnerAny \|\| (!partnerChosen && receiveIds.length === 0)` (whitespace-normalized comparison), and the note is inside the `merged` branch. Token presence is NOT enough (critic B-2: the one-character `\|\|`→`&&` sabotage keeps all three tokens while deleting the OQ-1 honesty on the untouched default) | **S-10a anyone-only-note:** gate the note on `partnerAny` alone; **S-10b conjunction-flip:** `partnerAny && (!partnerChosen && receiveIds.length === 0)` — both must go red |
| A-11 | Mirror adjacency: the count of `opponentChosenRef.current = true` sites equals the count of `setPartnerChosen(true)` sites, and each ref-write has a `setPartnerChosen(true)` within **±3 lines** (pinned window, N-1); `setPartnerChosen(true)` appears at no other site. **A-11b:** the `useRef(` and `useState(` declarations of the pair carry **textually identical initializer expressions** (post-R-10: `!!initialOpponentId && !seededPrefill` in both) | **S-11 drifting-mirror:** add a new tap site writing the ref without the state (payload scopes, note keeps claiming league-wide) — or write `setPartnerChosen(true)` from the default effect; **S-11b initializer-drift:** change one declaration's initializer only (pair diverges at mount on every prefill) |
| A-12 | The receive-side `TradeSide` call's `onAdd` body branches on `partnerAny` to `setTeamPickerOpen(true)`; `calc.receive-any-hint` exists with a `partnerAny`-gated render | **S-12 dead-end-add:** leave `onAdd={() => setPicker('receive')}` unconditional — Anyone's Add opens an empty picker |
| A-13 | The merged team-sheet **member-row** onPress body contains **all four** of `setPartnerAny(false)`, `opponentChosenRef.current = true`, `setPartnerChosen(true)`, `setOpponentId(o.user_id)` (critic B-3: nothing else pins the Anyone→member reset). Builder note (B-4): order the writes so the ref write stays within ~200 chars **before** `setOpponentId(o.user_id)` — FB-407's 20c-bis pairing window | **S-13 sticky-anyone:** drop `setPartnerAny(false)` from the member row — Anyone → member tap leaves `partnerAny` true while the ref scopes the payload: dropdown reads "Anyone", note renders, **wire targets one team** — a full honesty inversion, worse than the bug this item fixes |
| A-14 | The browse seeding effect's `setCanvasPrefill({…opponentId: rawTopCard.opponent_user_id…})` body (`TradesScreen.tsx`) contains `seeded: true`; **no other** `setCanvasPrefill(`/`loadCanvasPrefill(` site does; and `TradeBuildCanvas` passes `seededPrefill` on the `InLeagueCalculator` mount | **S-14 unmarked-seed:** drop `seeded: true` from the seeding write (the QA-B-1 bug returns: Clear-after-browse silently scopes) — or mark a tap site seeded (a chosen prefill stops scoping) |
| A-15 | Both chosen-ness initializers include the seed negation: the `opponentChosenRef` and `partnerChosen` declarations each contain `!seededPrefill` (redundant with A-11b's equality only if one of them does — the pair pins presence AND sameness) | **S-15 chosen-seed:** revert the ref initializer to `useRef(!!initialOpponentId)` — every seeded remount counts as chosen again |

Plus non-behavioral floor checks: existing suites (`check-calc-merged-behavior`,
`check-calc-partner-labels`, `check-inline-home`, `check-canvas-results`) all green;
`tsc --noEmit` clean; `testid-lint` green. **A-14 reads `TradesScreen.tsx` and
`TradeBuildCanvas.tsx` in addition to the calculator** — same `read()` helper, two
more files. The builder runs every sabotage as a red→green cycle (edit production
source, run suite, confirm the named assertion — and only it, where practical —
goes red, revert, confirm green) and logs the cycle in `TEST_LEDGER.md`.

**Enforcement honesty (N-3):** the `check-*.js` suites are `npm run`-only and
**gate nothing in CI today** (root CLAUDE.md §Stack; open NEXT.md item). CI runs
`pytest backend/tests`, bare `tsc --noEmit`, and `testid-lint`. Every
drift-proofing claim above binds only when the suite is run — the build agent MUST
run the full `mobile/tests` set explicitly before push and record it in
`TEST_LEDGER.md`; do not describe these pins as CI-enforced anywhere downstream.

### E-2 — Unit tests

**None new.** Backend diff is zero; the unscoped sweep is already covered by
`backend/tests/test_fair_packages.py` (partner-scope block `:15`, unscoped body
`:203`). Full `pytest backend/tests` green is the regression floor. No mobile pure
function is added (state transitions live in component handlers, covered by E-1).

### E-3 — Code-walk proof outline (builder executes at the shipped sha, file:line-cited)

1. Sheet Anyone tap → `setPartnerAny(true)` + `setOpponentId(null)` +
   `setTeamPickerOpen(false)` (new row, adjacent to the member-row handler at
   `InLeagueCalculator.tsx:1483-1488`); `opponentChosenRef` untouched.
2. `opponentId → null` rides the existing partner-change effect (`:579-585`) →
   `receiveIds` cleared, picker closed.
3. Default effect (`:546-548` + new guard) skips: `partnerAny` true.
4. Resolved `opponent` (`:587`) is null ⇒ dropdown reads "Anyone" (R-3 branch),
   `evalQ` disabled (`:613`), gated `ev` undefined ⇒ no verdict (`:1356`) / eveners
   (`:1306`) / lineup line / Suggested rows (`:634`), receive pool empty
   (`:595-600`), ✓ disabled (`:1272`). 4b. Scope-note predicate ⇔ payload-null
   equivalence shown term-by-term against the `:1229` gate.
5. Find a Trade (`:1220-1232`): `opponent` null ⇒ payload `opponent: null`.
6. `forkCanvasSearch` (`utils/canvasSearch.ts:41-69`): `has_partner: false`; path
   `fair` iff give side non-empty.
7. `handleInlineFindATrade` (`TradesScreen.tsx:3046-3073`) →
   `setSheetOpponent(null)` (`:3055`) → `scopedOpponent === undefined` (`:832-836`).
8. Fair: `runFairPackages` spread omits `opponent_user_id` (`:3353`); model:
   `generateMutation` sends `undefined` (`:1850`).
9. Server: `opponent_user_id = None` (`backend/server.py:12460`) → all-members
   opponents list (`backend/trade_service.py:5797-5803`) → per-idea counterparty
   (`:5816-5817`) → mixed-partner deck via `ideaToCard`, zero card changes.
10. Round trip: member-row tap → `partnerAny` false, ref + `partnerChosen` true,
    `opponentId` set → scoped behavior identical to pre-#406 (counter-case).
11. **Post-search browse session (B-1):** results land → seeding effect
    (`TradesScreen.tsx:5811-5823`) writes `{opponentId: counterparty, seeded:
    true, give, receive}` + `prefillSeq` bump → `TradeBuildCanvas` key bump
    (`:145-150`) → calculator remounts seeded, `partnerLocked`
    (`TradesScreen.tsx:5588`/`:7456`) → R-10 initializers set
    ref/`partnerChosen` **false**; in-session Find a Trade over the intact idea
    still scopes via the `receiveIds.length > 0` clause (`:1229`).
12. **Clear-after-browse (the QA-B-1 counter-case R-10 fixes):** canvas
    action-row Clear empties the sides without a remount → next Find a Trade:
    ref false, receive empty ⇒ payload `opponent: null` ⇒ league-wide restart
    (matches the #402 restart intent, `TradesScreen.tsx:5654-5657`); note
    renders. Session-end paths: pager Clear / exhaustion / Change restore blank
    or anchor prefill with no `opponentId` (`:5659`/`:5676`) and
    `scopedOpponent` null after an Anyone search ⇒ no pin-back.
13. NB-1 zero-results trace: no `rawTopCard` ⇒ no seeding ⇒ the
    `TradeBuildCanvas.tsx:168` key changes only if `scopedOpponent` changed —
    fresh-session Anyone display survives; a preceding scoped search remounts
    to honest default-unchosen (note visible, still league-wide).

### E-4 — Manual TestFlight checklist (operator; the only runtime evidence)

Written against the shipping runtime (`calc.canvas_results` LIT): found ideas
present **inside the canvas** as a browse session — a `N / X` chevron pager above
the canvas header, each fronted idea loaded into the canvas itself with its
manager in the (dimmed) Team dropdown. **There are no result cards below the
canvas** — verify counterparties by *paging*. "End the session" = the Clear by
the pager / anchor receipt (NOT the canvas action-row Clear, which step 6 uses
deliberately).

1. **Honest default (R-4 / #407 regression sentinel):** kill and relaunch; land
   on Trades. Touch nothing. *Expect:* under the Find a Trade / Clear / ✓ row a
   dim line reads "Find a Trade searches all teams — pick a team to target one."
   Tap **Find a Trade** on the empty canvas. *Expect:* the progress counts ALL
   leaguemates; when ideas load, **page with the chevrons** — the managers shown
   across pages are not all one team.
2. **Anyone row + unscoped fair sweep (R-1/R-3/R-5/R-6):** end the session. Add
   one of your own players to the send side. Tap the **Team** dropdown → the
   sheet's first row is "Any league mate — see offers from every team"; tap it.
   *Expect:* the dropdown reads **Anyone**, the receive column reads "any team"
   with the "Pick a team to add specific players…" hint line, and its **Add
   player** opens the team sheet (never an empty player list; after picking a
   team there you tap Add again — the picker does not auto-open, by design). Tap
   **Find a Trade**. *Expect:* ideas built around your player; paging shows
   **more than one** manager across the session.
3. **Scoped still scopes (R-8 / #384 checklist-23):** end the session (Change
   restores your anchor build, or rebuild it). Team sheet → pick a specific
   manager. *Expect:* the scope note is gone. Tap **Find a Trade**. *Expect:*
   every page of the session names only that manager.
4. **No dishonest verdict (R-7 — pre-search route; the dropdown is locked while
   a session is live, so run this with no session):** end any session. Pick a
   manager, put one of your players on the send side only. *Expect:* the
   one-sided read renders ("Trade options — from @them's roster" rows /
   consensus panel). Team sheet → **Any league mate**. *Expect:* the verdict
   panel, "Trade options"/"Recommended to even it" rows, and lineup-impact line
   all disappear — no leftover read against the old manager — and the ✓ cell is
   disabled.
5. **Round trip + reversibility (R-8/NB-1):** from step 4's Anyone state, tap
   **Find a Trade** (league-wide; the canvas then shows the top idea with its
   manager in the locked dropdown — correct: the "Anyone" label is
   pre-search-only). End the session. *Expect:* blank canvas, scope note
   visible. Pick a manager → search → scoped; end session; Anyone → search →
   league-wide. *Expect:* every search matches the state at tap time; nothing
   sticks across sessions.
6. **Clear-after-browse no longer scopes (R-10 — closes FB-407's known
   limitation):** run an untouched or Anyone search; let results land (the top
   idea seeds the canvas). Tap the **canvas action-row Clear** (the labelled
   Clear between Find a Trade and ✓ — NOT the pager's), then **Find a Trade**.
   *Expect:* the progress counts ALL leaguemates. (Pre-fix behavior was a
   single-team sweep of the seeded idea's manager — a "…/1" progress here means
   R-10 regressed.)
7. **Untouched elsewhere (R-9):** while an idea is on the canvas (live session),
   check the Team dropdown. *Expect:* dimmed and inert — no way into Anyone
   mid-browse; paging, ✕ pass with reasons, and ✓ queue behave exactly as
   today.

## Success criteria

1. Every R-1…R-10 pass criterion above holds; E-1 lands with all 15 assertions
   (A-1…A-15, incl. A-11b) green and every named sabotage cycle logged red→green
   in `TEST_LEDGER.md`.
2. CI green on the pushed sha: `pytest backend/tests`, bare `tsc --noEmit`, and
   `testid-lint` — **CI does not run the `check-*.js` suites** (N-3; root
   CLAUDE.md §Stack), so the build agent additionally runs the full
   `mobile/tests` set explicitly pre-push and records it in `TEST_LEDGER.md`.
   Backend diff is zero (`git diff backend/` empty); `TradesScreen.tsx` diff is
   exactly R-10's seed marker unless flagged per R-5; `TradeBuildCanvas.tsx`
   diff is exactly R-10's type field + prop pass-through;
   `mobile/tests/check-calc-merged-behavior.js` diff is exactly the declared
   20a re-spec (regex + hint text — critic B-4), nothing else in that suite.
3. Operator completes E-4 with all seven expectations met, logged in `TEST_LEDGER.md`.
4. Docs follow-through per [scope.md](scope.md) §4 (components/CLAUDE.md row,
   design components entry, DECISIONS.md entry).

## E-4 addendum (post-QA, QA-B B-1 — 2026-08-30)

8. **Zero-result wipe probe (known limitation):** end a *scoped* browse session
   (pick a manager, search, Done), then choose **Anyone**, hand-add 2+ give-side
   players WITHOUT searching, and tap **Find a Trade**. *Known limitation:* the
   canvas remounts as the search dispatches; if the sweep returns zero ideas the
   hand-built package is lost (the anchor receipt's "canvas still holds the
   assets" promise does not hold on this path). Wire scope and the scope note
   stay honest throughout. Host-key fix queued as a follow-up item.
