# Trade Calculator improvements — compressed plan (2026-07-03)

*enhance-app pipeline, right-sized: single feature (~800 LOC, authored 2026-07-02,
restyled to Chalkline same day). Phases 1–4 compressed into this doc; one
implementation wave (single implementer — the touched files overlap too much for
parallel agents); Phase 6 = tsc + web-preview regression.*

## Goal (Phase 1)

Make the demo Trade Calculator feel like a complete dynasty tool: no dead-end
states, draft picks (table stakes vs FantasyCalc/KTC/Dynasty Daddy), and make
the dual-board arbitrage mechanic *legible* instead of implicit. Demo-data only;
no backend. Success = flow verified end-to-end in preview with zero dead-ends.

## Findings (Phase 2 — self-audit, RICE-P ranked)

| # | Finding | Evidence | RICE-P |
|---|---|---|---|
| 1 | **Dead end once both sides are filled.** `suggestPackages` only fills the *empty* side; an UNEVEN/YOU_LOSE/THEY_DECLINE trade gets zero guidance. The core promise is "suggest fair offers" — it stops working mid-negotiation. | `tradeCalcMath.ts` `suggestPackages` forSide logic | High |
| 2 | **No draft picks.** Every competitor calculator has them; plan doc defers to v2 but demo-data makes it cheap: model a pick as an asset with young "age" so existing youth/vet board biases price it naturally. | `tradeCalcMock.ts` players-only | High |
| 3 | **Arbitrage is invisible.** Receive picker shows both values but the user must do mental math to spot bargains; send side never shows the partner's valuation at all. | `PlayerPickerModal.tsx` | Med-High |
| 4 | **Trade lost on unmount.** Leaving the Trades stack or killing the app discards the built trade. | screen `useState` only | Med |
| 5 | **No share/export.** RN `Share.share` is dependency-free. | — | Low-Med |

No reframing found: the feature works; the gaps are completeness, not a wrong
premise.

## Wave scope (Phase 3) — all five findings, one wave

Deferred: format toggle (1QB/SF), confidence ranges, animations — next wave.

## Design decisions locked (Phases 4–5)

- **Picks** = `CalcPlayer` with `pos: 'PICK'`, `age: 21` (youth-biased boards pay
  up, win-now fades — falls out of existing `ownerValue` math, zero new math),
  `nflTeam: '—'`, `pick: true`. Each team gets a 2027 1st/2nd/3rd. `CalcPos =
  Position | 'PICK'`; `PositionChip` already default-styles unknown positions.
  Meta line shows "Draft capital" instead of "— · 21 yrs".
- **Balance suggestions**: new `suggestAddOns()` in `tradeCalcMath.ts` — when both
  sides are set and the verdict isn't FAIR/WIN_WIN, propose 1–2 asset add-ons
  appended to the under-paying side (from that side's owner roster), scored with
  the existing `min(bothGains) − 0.5·|gap|` rule, FAIR/WIN_WIN survivors only.
  Rendered with the existing `SuggestionCard`; apply = append, not replace.
- **Arbitrage badges**: picker gains generic `badgeFor?: (p) => {label,color}|null`
  + `secondaryValue`/`secondaryPrefix` (replacing hard-coded `yourBoardValue`).
  Screen logic: receive picker → "TARGET" (`semantic.pos`) when my value ≥ 1.05×
  theirs; send picker → "SELL HIGH" (`flare.base`, informational per Chalkline
  rules) when their value ≥ 1.05× mine. Chalkline `Badge` renders them.
- **Persistence**: AsyncStorage key `ftf:tradecalc:v1` = `{partnerId, sendIds,
  receiveIds}`; hydrate-on-mount with id validation, fire-and-forget saves
  (same pattern as TradesScreen's `ftf:trades:fairness_on`).
- **Share**: RN `Share.share` text summary (sides + both boards' deltas +
  verdict), secondary Button shown only when both sides are set. No new deps.
- **Invariant**: `evaluateTrade` math and existing suggestion scoring unchanged —
  regression = same Bijan scenario numbers as the 2026-07-02 verification
  (2,536 / 2,874; +9% / +12%).

## Status

- [x] Plan
- [x] Implementation
- [x] Regression (tsc + preview flow, incl. Bijan parity check)
