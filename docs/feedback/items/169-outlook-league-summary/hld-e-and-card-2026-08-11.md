# #169 — HLD delta: frame E + card frame C

**Date:** 2026-08-11 · **Status:** planned
**Plan:** [`plan-e-and-card-2026-08-11.md`](plan-e-and-card-2026-08-11.md)

---

## Table of Contents

- [Architecture verdict: no change](#architecture-verdict-no-change)
- [Composition before / after](#composition-before--after)
- [Data flow](#data-flow)
- [Flag & contract surfaces](#flag--contract-surfaces)
- [Invariants this delta creates](#invariants-this-delta-creates)

---

## Architecture verdict: no change

Neither change adds a module, client, route, store class, or data flow. Both
are **composition moves inside existing components**:

- Frame E inserts a presentational strip in front of an existing section and
  adds one small persisted-preference store (`state/` pattern already used by
  `useTradeQueue` / `useFeedback` — AsyncStorage-backed, per-league keyed).
- The card change relocates two existing buttons across a screen/component
  boundary that both already share (`TradesScreen` owns `TradeCard`'s
  callbacks today — `onFlag`, `onEditInCalc`, etc.; `disposition` is one more
  callback prop of the same shape).

`docs/architecture.md` and `living-memory/HLD.md` therefore need **no
update** (recorded as "n/a because" rows in [`scope.md`](scope.md) §4).

## Composition before / after

### League Summary (flag `outlook.odds`, dark)

```
BEFORE                                   AFTER
basis toggle                             basis toggle
└─ oddsEnabled?                          └─ oddsEnabled?
   ├─ supported?                            ├─ supported?
   │  └─ SeasonOutlookSection               │  ├─ OutlookStrip  (collapsed default)
   │     (always fully open)                │  └─ expanded? SeasonOutlookSection
   └─ else OutlookUnsupportedRow            │     (unchanged internals)
chart card                                  └─ else OutlookUnsupportedRow
                                         chart card
```

`SeasonOutlookSection` is render-identical after one internal change: its
inline projected-standings sort (`:1801-1806`) is extracted to a
module-level `orderOutlookTeams()` that both the section and the strip call
(LLD §1.3) — same comparator, same rows, every existing testID, band rule,
cutline, and coverage caption survives. The strip is additive chrome in
front of it.

### Trade deck (no flag — direct UI change)

```
BEFORE                                   AFTER
deckWrap                                 deckWrap
├─ SwipableTopCard                       ├─ SwipableTopCard
│  └─ TradeCard                          │  └─ TradeCard
│     ├─ …header/fit/strength            │     ├─ …header/fit/strength
│     ├─ player tiles (split)            │     ├─ player tiles (split)
│     ├─ edit-in-calc                    │     ├─ ★ disposition row (Pass/Like)
│     ├─ TradeValueBar                   │     ├─ edit-in-calc
│     └─ reasons                         │     ├─ TradeValueBar
├─ Queue btn                             │     └─ reasons
├─ SendInSleeperButton                   ├─ Queue btn
├─ ★ dispositionRow (Pass/Like)          ├─ SendInSleeperButton
└─ hints / flag / share                  └─ hints / flag / share
```

The `match` variant (Dismiss + SendInSleeper actions) and the read-only
featured mount are untouched — they never receive the `disposition` prop.

## Data flow

Unchanged in both workstreams. The strip reads the **same** `outlookQuery`
result the section reads (one fetch, gated exactly as today). Pass/Like keep
calling the **same** `advance('pass' | 'like')` — the buttons move, the
handler, mutation, haptics, and deck-advance semantics do not.

## Flag & contract surfaces

| Surface | Change |
|---|---|
| `outlook.odds` | none — stays `false` in `config/features.json`; strip is inside its gate |
| Any other flag | none touched |
| API contracts | none — zero route/schema changes |
| Analytics events | **one new client event, `outlook_strip_toggled`** (operator rejected the waiver): mobile fires it from the strip toggle; `ALLOWED_CLIENT_EVENTS` in `backend/analytics_taxonomy.py` gains the name; tracking-plan addendum filed. Zero volume until `outlook.odds` lights. |

Consequence: the analytics-events surface IS touched, which is a CLAUDE.md
bright-line item — moot for express-eligibility (this build runs full gates)
but it obliges the taxonomy-first sequencing above. Everything remains fully
revertible by `git revert` (no data or flag state to unwind).

## Invariants this delta creates

Written into `docs/cross-client-invariants.md` at ship (W4):

1. **Deck disposition vocabulary is "Pass / Like"** (operator, §7 Q2) —
   testIDs `trades.pass-btn` / `trades.like-btn` are the cross-client names
   for this control pair; no client introduces "Accept/Decline" or
   "Send offer" for the deck disposition action. This binds VoiceOver
   strings too: the shipped `"Accept this trade"` accessibility labels
   (`TradesScreen.tsx:4761`, `:5427`) violate it and are renamed to
   "Like this trade" in W2 (LLD §2.2). Filed as its own invariants section
   ("Deck disposition"), not under the playoff-bands family.
2. **Card ordering rule:** Pass/Like sit directly beneath the player tile
   section; `TradeValueBar` sits below them; **any future card outlook block
   mounts below `TradeValueBar`** (operator: "value bar above the playoff
   outlook" — vacuous today, binding on whoever designs the deferred week-6+
   card treatment).
