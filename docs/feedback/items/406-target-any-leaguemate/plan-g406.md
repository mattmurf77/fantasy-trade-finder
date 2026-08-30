# Plan — G-406 "select any league mate as well as individual ones" (#406)

> Planner output, 2026-08-30. Tree verified against `origin/main` @ `e89eebb0`.
> Report (jonbonjourvi, screen `TradesHome`, v1.16.10, severity polish):
> *"Let you select any league mate as well as individual ones. So that it shows
> you all options for the player you're trying to move."*
> Batch context: [plan.md](plan.md) (G-406 + G-407 run, 2026-08-30).

## 1. Problem statement

On the merged Trades landing (`TradesHome`, flags `calc.merged_layout` +
`calc.inline_home` + `calc.canvas_results`, all LIT on v1.16.10), the way to
"shop a player" from the canvas is: put the player on the give side, and tap
**Find a Trade**. The canvas's **Team dropdown always holds exactly one league
mate** — it defaults to the first opponent the moment rosters load
(`mobile/src/components/InLeagueCalculator.tsx:538-541`) and its picker sheet
lists only individual members (`InLeagueCalculator.tsx:1451-1494`), with no
"anyone" row and no way back to an unscoped state. So the fairness sweep is
always scoped to that one team (`TradesScreen.tsx:3353`), and the user must
cycle partners one by one to see "all options for the player you're trying to
move."

Everything below that picker already supports the unscoped run. The gap is one
missing row in one sheet.

## 2. Which surface the report maps to

Three candidate readings were checked against current code:

| Candidate | Finding | Verdict |
|---|---|---|
| **Canvas Team dropdown on the merged landing** | Single-partner is forced: default-to-first effect (`InLeagueCalculator.tsx:538-541`), individual-only sheet (`:1451-1494`), dropdown label `@user` or `Choose…` (`:987`) — never "anyone". | **This is the report.** Screen tag `TradesHome` matches (the shop window stamps `ShopAsset` on its own FAB, `ShopAssetScreen.tsx:72`, so the report was not filed from there). |
| Shop window (#402/#403, `ShopAssetScreen`) | Already league-wide: `ShopOffersBody.tsx:383-411` sends **no** `opponent_user_id`, and `/api/trades/asset-ideas` unscoped sweeps all members (#250 fix; `docs/feedback/items/250-team-targeting/status.md`). | No gap — nothing to build. |
| Deck team-targeting (Specific Team / targeting sheet) | An "all teams" state already exists: the guided deck is unscoped by default, and the sheet's team scope is tap-again-to-clear (`TradesScreen.tsx:8648`). | No gap; an explicit "Any team" row there is a discoverability nicety, held as OQ-3. |

## 3. What the backend already does (verified, file:line)

The league-wide sweep for a hand-built give side is **shipped, documented, and
tested** — the client picker is the only thing that can't reach it:

- Route: `POST /api/trades/fair-packages` — `opponent_user_id?` … *"omitted ⇒
  every league-mate with a roster"* (`backend/server.py:12398-12399`; parsed at
  `:12460`, passed through at `:12520`).
- Impl: `_generate_fair_packages_impl` builds `opponents` as **all** members
  with rosters and only narrows when a scope is given
  (`backend/trade_service.py:5797-5803`), then sweeps each (`:5837`). Ideas
  carry `counterparty_user_id`/`counterparty_username` per idea (`:5816-5817`),
  so a mixed-partner deck renders correctly with zero card changes.
- Tests: `backend/tests/test_fair_packages.py:15` ("PARTNER SCOPE —
  `opponent_user_id` limits the sweep"), unscoped body at `:203`.
- Docs: `docs/api-reference.md` fair-packages row already says *"or from every
  league-mate's when no partner is named."*
- The model path (empty canvas) is likewise partner-optional: a calculator
  arrival generates "even with no opponent chosen" (`TradesScreen.tsx:2994-3001`).

And the client plumbing between the picker and the wire is already null-safe:

- `onFindATrade` passes `opponent: … | null` (`InLeagueCalculator.tsx:1212-1218`).
- `forkCanvasSearch` types opponent nullable and reports `has_partner`
  (`mobile/src/utils/canvasSearch.ts:44-48, :57` — no new analytics needed).
- `handleInlineFindATrade` adopts it via `setSheetOpponent(fork.opponent)`
  (`TradesScreen.tsx:3055`); `scopedOpponent` derives to `undefined`
  (`:832-836`); `runFairPackages` spreads the key only when set (`:3353`).

**The single blocker** is UI state: `opponentId` can never return to null once
`opponents` load (`InLeagueCalculator.tsx:538-541`), and the sheet offers no
unscoped choice.

## 4. Work-type verdict: POLISH

Client picker extension over existing backend capability. Zero backend diff,
zero schema, zero new routes, zero analytics-taxonomy change (`has_partner:
false` on the existing `calc_find_a_trade_tapped` already encodes the unscoped
run), zero new feature flag proposed (the row lives inside the
`calc.merged_layout` surface and dies with it; the CLAUDE.md bright line —
schema / API contracts / flag surfaces / analytics events — is untouched).
Deciding citations: `backend/server.py:12398-12399` +
`backend/trade_service.py:5797-5803` (capability exists) vs
`InLeagueCalculator.tsx:538-541, :1451-1494` (constraint is picker-local).

Full gates still apply (no express declared): scope block, evidence delta, docs
table, ledger — the Author agent writes the PRD/scope from this plan.

## 5. Approach

Add an **"Any league mate" row** to the merged team sheet, backed by an
explicit unscoped state that resolves `opponent` to `null` for everything
downstream (all of which is already null-safe or already correctly disabled).

Mechanics (LLD altitude, for the Author to refine):

1. `InLeagueCalculator` partner state gains an explicit unscoped value —
   suggested: keep `opponentId: string | null` and add a
   `partnerAny: boolean` (or a `'any'` sentinel; the boolean avoids sentinel
   leakage risks). The default-to-first effect (`:538-541`) must skip when the
   user chose Anyone.
2. Team sheet (`calc.team-sheet`, `:1448`): a leading row
   (`calc.team-sheet.any`) above the member rows; tapping sets unscoped and
   closes. Member rows unchanged (keeps `check-calc-partner-labels.js` green).
3. Team dropdown (`calc.team-dropdown`, `:964-991`): label reads **"Anyone"**
   in the unscoped-by-choice state (today's `Choose…` remains only for the
   pre-load frame), with a matching a11y label.
4. Downstream honesty under Anyone — all by existing gates, verify not build:
   - ✓ queue cell stays disabled: expression at `:1258`
     (`!onLikeTrade || !bothSides || !opponent || queueing`) is **untouched**
     (it is pinned by `check-calc-merged-behavior.js` 18-19d and the
     components/CLAUDE.md "anything broader" warning).
   - Live verdict / eveners / lineup impact don't fetch: `enabled:
     !!opponentId` (`:606`) — must gate on a *resolved* partner, never a
     sentinel.
   - Receive-side "+ Add" pool is `rosterByOwner[opponentId]` (`:589-592`) —
     empty under Anyone; render a one-line hint ("Pick a team to add specific
     players — Find a Trade shows offers from everyone"). OQ-2 offers the
     bigger alternative.
5. `TradesScreen`: expected **zero diff** — `handleInlineFindATrade`
   (`:3046-3073`) and `runFairPackages` (`:3347-3354`) already handle the null
   partner. If the scoped-empty / anchor-receipt copy needs an "Anyone"
   variant, that is the only candidate edit; flag it to the orchestrator if it
   materializes.

### Alternatives considered

- **Do nothing / point users at the shop window** — the shop window is already
  league-wide, but it is reachable only from a deck card's give-side "More
  offers" (`trade.shop_asset` conjunction) and the report was filed from the
  canvas flow; the canvas would still silently scope to a team the user never
  chose. Rejected.
- **League-wide receive pool under Anyone** (picking any leaguemate's player
  auto-resolves the partner to that owner) — genuinely nice, matches FB-47's
  acquire-pool precedent, but it is a second feature (pool build, owner
  resolution, mixed-owner conflicts) stapled to a polish item. Held as OQ-2.
- **Make Anyone the default** — behavior change for every canvas run and
  overlaps #407's regression question; operator call, not a planner call
  (OQ-1).
- **New feature flag** — the row is a picker option inside an already-flagged
  surface with a one-line revert; a flag would add a key + docs + guard forever
  for a row. Rejected (Author may re-raise in the scope block if the operator
  wants it).

## 6. Interaction with #407 — read before building

#407 (mattmurf77, v1.16.11, fast-track bug): *"The find a trade feature is
incorrectly forcing a team from the calculator screen below it."* That is the
**same root behavior** seen as a bug: the default-to-first effect
(`InLeagueCalculator.tsx:538-541`) silently scopes Find a Trade to a partner
the user never chose. #406 is the explicit-control half; #407 is the
default-behavior half.

Consequences:

- **Serialize: land #407 first, rebase #406 on it.** #407's fix almost
  certainly edits `InLeagueCalculator.tsx` (the default-select effect and/or
  how the untouched dropdown feeds `onFindATrade`) and possibly
  `TradesScreen.tsx:3046-3073` — the exact lines this plan builds on. Parallel
  build would conflict on the same functions.
- If #407 resolves as "an untouched dropdown does not scope the sweep," then
  #406's remaining scope shrinks to the explicit affordance: the Anyone row,
  the honest "Anyone" dropdown label, and the way back to unscoped after
  choosing an individual — which is still worth shipping (the state must be
  visible and reversible, not just default).

## 7. Platforms touched

Mobile only. Backend: none. Web/extension: no equivalent canvas surface.

## 8. File-ownership proposal

| File | G-406 role | #407 overlap risk |
|---|---|---|
| `mobile/src/components/InLeagueCalculator.tsx` | **Primary edit** (state, sheet row, dropdown label, receive-pool hint) | **HIGH — same file, likely same effect. Serialize behind #407.** |
| `mobile/tests/check-any-partner.js` (new) + `mobile/package.json` (script row) | New structural guard | None |
| `mobile/src/screens/TradesScreen.tsx` | Expected zero diff (read-adjacent; possible copy variant only) | HIGH if a diff materializes — declare before editing |
| `mobile/src/utils/canvasSearch.ts` | Zero diff (verified null-safe) | Low |
| `mobile/src/components/CLAUDE.md` (InLeagueCalculator row), `docs/feedback/items/406-target-any-leaguemate/*` | Docs | None |

Not touched (named to prove non-overlap with the #402 shop files):
`ShopOffersBody.tsx`, `ShopAssetScreen.tsx`, `shopMode.ts`, `backend/*`.

## 9. Risks

- **#407 collision** — §6; serialize.
- **Pinned guards**: `check-calc-merged-behavior.js` 18-19d pins the ✓
  disabled expression; `check-calc-partner-labels.js` pins the partner-row
  construction; `check-inline-home.js` §11 pins host-gating. The build must
  leave all green — the Anyone row is additive, not a rewrite of member rows.
- **Sentinel leakage**: if a sentinel id is used instead of a boolean, it must
  never reach `evaluateTradeInLeague`, `queueCalcTrade`, or any request body.
  Guarded structurally (E-1 below).
- **`partnerLocked` browse state** (#402 canvas-results: an idea's counterparty
  is fixed): the dropdown is already inert there (`:972`); Anyone must not be
  reachable while locked — comes free with the existing `disabled`.
- **Stacked (non-merged) layout**: keeps individual-only (it is an
  evaluate-first surface with no Find a Trade row, `:1201`); change is scoped
  to the `merged` branch.

## 10. Spikes

None. The load-bearing capability is proven by shipped tests
(`test_fair_packages.py:203`) and the route docstring; no unknowns requiring a
throwaway build.

## 11. Draft requirements (R-1…) with D-056 evidence sketch

Maestro and the simulator are retired (D-056) — evidence is structural guards,
unit tests, a code-walk proof, and an operator TestFlight checklist.

- **R-1 — Anyone row.** The merged team sheet renders a leading
  "Any league mate" row (`calc.team-sheet.any`); tapping it sets the unscoped
  state and closes the sheet. Member rows byte-identical.
- **R-2 — Honest dropdown.** In the unscoped-by-choice state the Team dropdown
  reads "Anyone" (a11y label matching); `Choose…` remains only pre-load.
- **R-3 — Unscoped run.** With Anyone active, Find a Trade sends **no**
  `opponent_user_id` on the fair path (and no scope on the model path); the
  resulting deck may contain multiple counterparties. No new analytics —
  `calc_find_a_trade_tapped.has_partner: false` is the existing signal.
- **R-4 — No dishonest states.** Under Anyone: ✓ cell disabled via the
  untouched `:1258` expression; verdict/eveners/lineup queries do not fire;
  receive-side add shows the hint line; no request body ever carries a
  sentinel value.
- **R-5 — Round trip.** Picking a named member from the Anyone state restores
  today's scoped behavior byte-identically (scoped sweep, receive pool,
  verdict, ✓ eligibility).
- **R-6 — Byte-identical elsewhere.** Stacked layout, `FeaturedTradeWindow`
  host, the #270 experiment mount, and the `partnerLocked` browse state are
  unchanged; flag-off (`calc.merged_layout` false) is unreachable-by-construction.

Evidence sketch:

- **E-1 structural** — new `mobile/tests/check-any-partner.js` (+ `npm run`
  script): (a) `calc.team-sheet.any` row exists in the merged sheet; (b) the
  default-to-first effect is guarded on the unscoped state; (c) the ✓
  `disabled` expression is textually unchanged; (d) the eval query's `enabled`
  requires a resolved partner; (e) no sentinel string appears in any
  `api/`-bound call site; (f) `runFairPackages`' conditional spread of
  `opponent_user_id` is intact. Plus: existing `check-calc-merged-behavior.js`,
  `check-calc-partner-labels.js`, `check-inline-home.js`, `check-canvas-results.js`
  all stay green; `tsc --noEmit` clean; `testid-lint` (new testID registered).
- **E-2 unit** — backend zero-diff; the unscoped sweep is already covered by
  `backend/tests/test_fair_packages.py` (partner-scope block, `:15`, `:203`).
  Full `pytest backend/tests` green as the regression floor.
- **E-3 code-walk proof** (written at ship, file:line-cited): Anyone tap →
  `opponent: null` in the `onFindATrade` payload
  (`InLeagueCalculator.tsx:1212-1218`) → `forkCanvasSearch`
  (`canvasSearch.ts:44+`) → `setSheetOpponent(null)` (`TradesScreen.tsx:3055`)
  → `scopedOpponent === undefined` (`:832-836`) → request body without
  `opponent_user_id` (`:3353`) → `opponent_user_id = None`
  (`server.py:12460`) → all-members sweep (`trade_service.py:5797-5803`).
- **E-4 operator TestFlight checklist** (runtime proof): (1) TradesHome, add
  one give-side player, Team dropdown → "Any league mate" → dropdown reads
  Anyone; (2) Find a Trade → result cards name more than one manager;
  (3) pick a specific manager instead → every result names only that manager;
  (4) under Anyone the ✓ confirm cell is disabled and no verdict bar renders;
  ✓ on a result card queues to that card's counterparty with the normal toast;
  (5) return to Anyone after a scoped run — next Find a Trade is league-wide
  again.

## 12. Open questions for the orchestrator/operator

- **OQ-1** — After #407 lands: should the *default* (untouched) scope be
  Anyone, or stay first-opponent with Anyone as an explicit choice? (Changes
  every canvas run; operator ruling.)
- **OQ-2** — Receive side under Anyone: hint-only (this plan) or a league-wide
  receive pool that auto-resolves the partner from the picked asset's owner
  (bigger, deferred)?
- **OQ-3** — Also add an explicit "Any team" row to the deck's targeting-sheet
  team picker for discoverability (functionally redundant with
  tap-again-to-clear, `TradesScreen.tsx:8648`)? Out of scope unless ruled in.
