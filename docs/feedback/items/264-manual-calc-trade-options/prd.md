# FB-264 — Manual calculator shows no trade options on a one-sided trade

- **Screen:** TradeCalculator (app v1.11.0) · **Type:** bug
- **Report:** "The manual calc should still show the different trade options."
- **Status:** implemented 2026-08-08 (branch `teardown-remediation` worktree — see `status.md`)

## 1. What "trade options" resolves to

The report names no component, so this section pins the term with evidence
from the shipped surfaces rather than guessing.

"Different trade options" = **the concrete, one-tap alternative assets the
calculator offers alongside the verdict** — the family of rows/cards this
surface has shipped under three names:

| Surface | Component | Where it renders |
|---|---|---|
| "Recommended to even it" | `EvenerRows` | In-league mode (above the verdict since #251), live mode inside `ConsensusVerdictCard` |
| "To balance — add from …" | `SuggestionCard` list | In-league mode (`balanceQ`), live mode (`addOns`) |
| "Fair returns / Fair offers (consensus)" | `SuggestionCard` list | **live + demo modes only** (`suggested`) — whole alternative packages for the other side |

Evidence that this is the operator's own vocabulary for these rows:

- `docs/feedback/items/251-evener-placement/status.md` — the operator filed
  "Recommended to even it should be right underneath the trade window itself"
  after the deck's featured-window hand-off; the eveners are the thing the
  operator watches for on this screen.
- `docs/feedback/items/157-calc-value-clarity/status.md` — the value bar's own
  copy frames the gap as **a counteroffer** ("Ask them to add ≈ a 2nd to even
  it out"); the eveners are that sentence made tappable.
- `docs/feedback/items/204-calc-value-bar/status.md` — the standing rule for
  this screen: every trade surface carries the same verdict furniture. #264 is
  the same complaint one level down — the *options* furniture is not on every
  state of the surface.

## 2. Repro

In-league mode (the mode a league user lands in from the deck's "Edit in
calculator", and the only mode with real rosters):

1. Calculator → **In league** → pick a partner.
2. Add one or more players to **You send**. Add nothing to **You receive**.
3. Observe: the verdict card reads "Add a player to each side for a verdict."
   and **nothing else renders** — no evener rows, no balance suggestions, no
   alternative packages. The screen offers zero options until the user
   themselves guesses what to ask for.
4. Same in reverse (fill only **You receive**).

Contrast — **live ("Real values") mode**, same one-sided state: the
"Fair returns (consensus)" `SuggestionCard` list renders whole alternative
packages for the empty side (`TradeCalculatorScreen` `livePkgForSide` /
`suggested`). So the screen shows options in one mode and not the other, which
is exactly "the manual calc should **still** show the different trade options".

## 3. Root cause

`POST /api/trade/evaluate` only computes `favors` / `gap` when **both** sides
are non-empty (`backend/server.py`: `if give and recv:` guards the
`_value_verdict_payload` call). Everything the In-league calculator renders
below the trade window is gated on that gap:

- `EvenerRows` requires `ev.gap?.add_to` (`InLeagueCalculator.tsx`, the #251 block).
- `balancePlan` returns `null` unless `debGive.length > 0 && debReceive.length > 0`.

So a one-sided in-league read is structurally optionless. Live mode escapes
this only because its package suggestions are computed **client-side** over
the top-40 consensus pool (`rankPackageCandidates`), which needs no gap.

The backend already solved this for a different caller: `one_sided_eveners:
true` (Mode B, 2026-07-27 deck player-changer) builds eveners for the **empty**
side from that side's owner's real roster + owned picks, sized against the
non-empty side's package value (`_roster_eveners`: value window 0.4–1.5×,
≤3 singles + at most one 2-piece combo, the owner's untouchables excluded).
Today the only client that sends it is `evaluateForSwapSuggestions`
(SwapSuggestSheet). The calculator — the surface whose entire job is building
a trade one side at a time — never asks for it.

## 4. Fix

**Ask the server for the options it can already build, and render them in the
slot that already exists.** No new card, no new section, no new endpoint.

- **R-1 — request them.** The In-league calculator's evaluate call sends
  `one_sided_eveners: true`. Two-sided reads are byte-identical (the backend
  branch is an `elif` gated on `bool(give) != bool(recv)`); old servers ignore
  the key and the client degrades to today's empty state.
- **R-2 — render them in the SAME slot.** The existing `EvenerRows` mount
  (directly under the trade window, above the fairness summary — the #251
  order, unchanged) also serves the one-sided case. **One block, not two** —
  consolidation per #205, no new cards appended to the stack.
- **R-3 — honest label.** Two-sided uneven keeps today's copy verbatim
  ("Recommended to even it — add from your roster" / "— ask @x to add"). The
  one-sided case says what it actually is: **"Trade options — from your
  roster"** / **"Trade options — from @x's roster"**. These assets are not
  "evening" anything; they are candidate returns worth roughly what the filled
  side is worth.
- **R-4 — the + still works.** Tapping + adds the asset(s) to the empty side
  (their roster → You receive; your roster → You send) and the debounced
  re-evaluate turns the read two-sided, at which point the rows become the
  normal eveners for the resulting gap. Derived from the response itself
  (`ev.per_player` side counts), never from possibly-newer local state, so the
  rows and the target side can never disagree with the payload that produced
  them.
- **R-5 — nothing else moves.** Live mode, demo mode, `EvenerRows`,
  `ConsensusVerdictCard`, the balance suggestions, the verdict card and every
  testID are untouched.

## 5. Data limitations — stated, not faked

- **These rows are consensus-priced.** `_roster_eveners` values candidates with
  the pool `seed_value`, not the two personal boards, in the one-sided case
  exactly as in the shipped two-sided case. The screen makes no personalized
  claim about them; the two-board read stays where it is — in the verdict card,
  which needs both sides to exist. Nothing new is asserted about the partner's
  opinion of these assets.
- **Not implemented: whole alternative PACKAGES in Mode B** (live mode's "Fair
  returns"). Mode B has no client-side package search, and building one would
  mean either a fresh server sweep (that is `/api/trades/asset-ideas`, i.e. the
  finder) or an unconfirmed client ranking next to a server-authoritative
  verdict — the #78 rule this screen was explicitly built to obey. The honest
  equivalent with the data on hand is the single-asset + one-combo evener set
  above. If the operator wants full packages here, the existing path is the
  #213 "Want ideas instead? Find a trade →" link, which is already on screen.
- **A fair two-sided trade still shows no options.** By design: there is
  nothing to even, and the balance suggestions cover the uneven case.

## 6. Regression risk

Byte-identical in every state except the one-sided in-league read. The
`one_sided_eveners` server branch is 2026-07-27 code already in production
behind SwapSuggestSheet.

## 7. Maestro regression flow

`mobile/.maestro/flows/regression/264-calc-one-sided-options.yaml` (spec — the
batch QA round owns authoring/running it; this build is static-verified only):

1. Launch → sign in (smoke profile) → `tab.trades` → `trades.finder-mode.calc`.
2. `calc.mode-tab.league` → wait for `calc.league-give-add`.
3. Tap `calc.league-give-add` → `calc.picker.search` type a rostered player →
   tap `calc.picker.row.<player_id>` → `calc.picker.done`.
4. **Assert:** at least one `calc.evener.*` row is visible, and the text
   "Trade options" is visible. (Pre-fix: neither exists.)
5. Tap the row's `calc.evener-add.<id>` → assert the asset appears on
   **You receive** and the verdict card resolves (`calc.verdict` content /
   "Consensus" totals row).
6. **Assert:** the rows are now the two-sided set — "Recommended to even it"
   text visible (or no rows at all if the trade came out even) and "Trade
   options" gone.
7. Boundary: `calc.mode-tab.live` → build a one-sided package → assert the
   live-mode suggestion list still renders (unchanged behavior).
