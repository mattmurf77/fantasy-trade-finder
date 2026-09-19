# #78 — Calculator suggestions disagree with the evaluator

**Covered feedback IDs:** #78 (build) · #87, #88 (verify-close)
**Branch:** trade-engine-v2 · **Date:** 2026-07-17
**Status:** built; typecheck clean; math verified numerically against the
fixture backend; on-device (sim) confirmation DEFERRED to the batch QA round
per orchestrator directive (shared-harness contention) — see the QA checklist
at the bottom.

## The bug (#78, confirmed)

> "The suggestions are straight value sums. The actual received value of a
> trade seems to be evaluated differently, leading to bad add suggestions."

Exactly right. Two different maths coexisted in the calculator's live mode:

- **Verdict** — server-authoritative `POST /api/trade/evaluate` (Mode A/B),
  which prices packages with the v2 engine's `package_value_v2`: each asset
  contributes `v · (0.15 + 0.85·(v/v_max)^γ)` with `v_max` the best single
  asset in the whole trade (γ = `package_adj_gamma`, default 1.5, plus a
  flag-gated crown-asset premium). Verdict from the min/max package ratio:
  ≥ 0.95 even, ≥ 0.75 fair, else unfair.
- **Suggestions** (`suggestAddOns` / `suggestPackages` in
  `mobile/src/utils/tradeCalcMath.ts`) — flat `PKG_WEIGHTS`
  `[1, .88, .78, .7, .64, .6]` weighted sums with ±2/4 % delta bands. No
  relation to the server's nonlinear discount.

### Measured disagreement (fixture backend, standard profile, 1QB PPR)

Trade: Ja'Marr Chase → J.K. Dobbins (server: ratio 0.009, unfair).
Top-3 add-ons the OLD local math labelled "Fair trade":

| Old suggestion (labelled FAIR locally) | Server verdict |
|---|---|
| + Trey McBride, Jordyn Tyson | **unfair**, ratio 0.478 |
| + Drake Maye, Christian McCaffrey | **unfair**, ratio 0.474 |
| + Kenneth Walker, George Pickens | **unfair**, ratio 0.478 |

Every card the old UI showed as fair was scored unfair by the very evaluator
rendered directly above it — the "bad add suggestions" of the report.

## The fix

Suggestions now agree with the evaluator by construction, via a two-stage
pipeline (chosen over pure local replication because `package_value_v2` is
nonlinear and server-config/flag tunable — γ and the crown-asset premium can
change without a client release, so **server confirmation is mandatory**):

1. **Shortlist locally** with a mirror of the server's v2 package math
   (`packageValueV2` / `consensusRatio` / `rankAddOnCandidates` /
   `rankPackageCandidates` in `tradeCalcMath.ts`) — ranking heuristic only.
2. **Confirm every shortlisted combo** through the same
   `POST /api/trade/evaluate` the verdict uses (`evaluateTrades` /
   `evaluateTradesInLeague` in `mobile/src/api/calc.ts`, chunked 4 at a
   time), and only render candidates the server scores **fair/even**; add-ons
   must additionally **strictly improve the server's `point_ratio`** over the
   current trade. A suggestion can therefore never propose an add the
   evaluator would score as making the trade less fair.
3. Confirmation is gated on the base evaluation being settled (no stale-ratio
   comparisons), and confirmed cards are never kept as placeholder data for a
   different trade.

Demo mode is untouched: its verdict panel IS the local dual-board math, so
local suggestions already agree with it by construction.

### Pipeline check (same fixture trade)

New shortlist top-8, mirror-predicted vs server-confirmed:

| Candidate add | Mirror predicted | Server |
|---|---|---|
| Amon-Ra St. Brown + Jaylen Waddle | 1.000 | 1.000 even |
| Puka Nacua + Patrick Mahomes | 0.999 | 0.999 even |
| CeeDee Lamb + Patrick Mahomes | 0.999 | 0.999 even |
| …(all 8) | ±0.001 | all even/fair, all kept |

Mirror tracks the server to 3 decimals; every rendered card is
server-confirmed.

## Files changed

- `mobile/src/utils/tradeCalcMath.ts` — v2-mirror math + candidate ranking
  (`packageValueV2`, `consensusRatio`, `rankAddOnCandidates`,
  `rankPackageCandidates`, `rankGapCandidates`) + display adapters
  (`evalFromConsensus`, `evalFromBoards`). Legacy demo-mode functions
  untouched.
- `mobile/src/api/calc.ts` — `TradeProbe`, `evaluateTrades`,
  `evaluateTradesInLeague` (chunked confirmation, failed probe → dropped).
- `mobile/src/screens/TradeCalculatorScreen.tsx` — live mode: suggestions now
  come from the shortlist→confirm query (`calc-suggest`); the lighter side
  for add-ons comes from the server's own `gap.add_to`. Demo mode keeps the
  local suggester.
- `mobile/src/components/InLeagueCalculator.tsx` — NEW balance section
  (#88 gap): Mode B-confirmed 1–2-piece add-ons from the lighter side's real
  roster; divergence basis requires the worse-off board's delta to strictly
  improve AND consensus fair/even; testIDs `calc.league-give-add` /
  `calc.league-receive-add` registered in `mobile/src/components/CLAUDE.md`.
- `mobile/src/components/ConsensusVerdictCard.tsx` — no change needed.

## #87 / #88 verdicts (code-verified; on-device confirmation deferred)

- **#87 (league picker + partner roster selection): SATISFIED (in code).**
  `InLeagueCalculator` renders: the session league (chosen via LeaguePicker —
  the "In league" mode tab only appears with a league session); a "Trade
  partner" chip row listing every leaguemate (unranked members flagged with a
  flare dot + consensus-fallback note); and give/receive pickers scoped to
  YOUR real roster and the selected partner's real roster
  (`rosterByOwner[userId]` / `rosterByOwner[opponentId]`).
- **#88 (bottom section suggests players to balance the lesser side within a
  fair range): gap fixed (in code).** Before this change the balance section
  existed only in live/demo modes and used the disagreeing local math (#78);
  the In-league mode had none. Now: live mode's section is server-confirmed,
  and In-league mode gained its own "To balance" section drawing from the
  lighter side's actual roster, confirmed by the same Mode B evaluate call
  that renders the verdict ("fair range" = the evaluator's own fair/even
  band, plus strict improvement for the worse-off board / point ratio).

## Evidence

- Numeric before/after probes against the fixture backend (standard profile,
  port 5003-local, no shared-harness touches) — tables above: old suggestions
  all server-**unfair** (ratio ~0.47); new pipeline's suggestions all
  server-**even/fair**, mirror within ±0.001 of the server.
- `cd mobile && npx tsc --noEmit` clean.
- Sim screenshots NOT captured this round (harness contention; orchestrator
  deferred to batch QA). Scratch Maestro flows for both legs are ready:
  `78-before.yaml` / `78-after.yaml` (session scratchpad) — the after flow is
  reproduced below as the QA checklist.

## QA checklist (batch QA round — exact checks)

Profile `standard`, user `qa_standard`, league `990000000000000001`, 1QB PPR.

1. **Live mode, #78:** Trades → Calculator → "Real values". Side A: Ja'Marr
   Chase (7564). Side B: J.K. Dobbins (6806). Expect verdict "Uneven" and a
   "To balance — add to Side B" section whose cards are server-confirmed
   (each card, applied, must yield a **fair/even** verdict — assert the
   verdict card does NOT read "Uneven" after applying the top card).
   Regression guard: no card may name two mid-tier players (e.g. McBride +
   Tyson) — that was the old straight-sum failure mode; expect near-Chase
   packages (e.g. Amon-Ra St. Brown + Jaylen Waddle).
2. **Live mode, one-sided:** clear, add only Chase to Side A → "Fair returns
   (consensus)" cards; applying any card must yield fair/even verdict.
3. **In-league mode, #87:** switch to "In league" tab (testIDs
   `calc.mode-tab.league`, `calc.league-give-add`, `calc.league-receive-add`).
   Confirm partner chips (@qa_opp_ranked, @qa_opp_unranked, …), unranked dot
   on @qa_opp_unranked, give picker = qa_standard's roster only, receive
   picker = selected partner's roster only.
4. **In-league mode, #88:** partner @qa_opp_ranked; give Chase (7564),
   receive Trey McBride (8130) → two-board verdict + "To balance — ask
   @qa_opp_ranked to add" section (adds drawn from qa_opp_ranked's roster
   only). Applying a card must improve the verdict (mutual-gain/fair — never
   a worse read). With @qa_opp_unranked selected, basis degrades to
   consensus and the section must respect the consensus fair band instead.
5. **Demo league mode:** unchanged behavior (local dual-board suggestions —
   self-consistent with the demo verdict panel).
