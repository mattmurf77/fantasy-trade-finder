# #157 — Calculator value clarity (Value Bar trade verdict)

**State:** built (component + calculator wiring), typecheck clean. Presentation-only.

## Covered feedback IDs

- **#157** — calculator value clarity: reframe the fairness read as pick-denominated value.
- **#169 (value-bar piece)** — the "Value Bar — Trade Verdict" mockup. This delivers
  #169's **trade-verdict** component; #169's league-summary bar-chart work lives
  separately under `docs/feedback/items/169-outlook-league-summary/`.

## What shipped

A **reusable** `TradeValueBar` component + its first wiring into the calculator verdict.

- **New:** `mobile/src/components/TradeValueBar.tsx` — a diverging value bar centered
  on "even" with pick-landmark ticks (−1st / −2nd / Even / +2nd / +1st, scale = ±1
  generic Mid 1st), a directional fill toward the winning side, a "who wins" headline
  (You win / They win / Even), and the margin in pick terms ("You win by +4,520 · ≈ a
  Mid 2nd") plus a counteroffer line ("Accept as-is, or offer a small give-back" /
  "Ask them to add ≈ a 2nd to even it out").
- **Wired:** `mobile/src/components/ConsensusVerdictCard.tsx` (calculator **live**
  mode, `TradeCalculatorScreen` `calc.verdict`). The old single-direction fairness
  headline + gap-note is replaced by `TradeValueBar`; the raw give/get totals stay
  below as secondary reference. One-sided packages (no gap) keep the "Package value"
  fallback.

Design source-of-truth: `mockups/outlook-odds/value-bar.html` (approved), with the
tier-chip detail from `mockups/calc-value-clarity/tilt-bar.html`.

## Interface (reuse contract)

```ts
interface TradeValueBarProps {
  giveValue: number;                              // give_value
  receiveValue: number;                           // receive_value
  favors: 'give' | 'receive' | 'even' | null;     // authoritative who-wins
  gap: CalcGap | null;                            // { value, add_to, firsts, pick_equivalent }
  youLabel?: string;  themLabel?: string;         // perspective wording (default You/They)
}
```

## Exact `/api/trade/evaluate` fields used (verified against backend)

- `give_value`, `receive_value` — side totals (server route `trade_evaluate_route`).
- `favors` — `'receive'` = you win, `'give'` = they win, `'even'`/`null` = balanced.
- `gap.value` — absolute package-value delta.
- `gap.firsts` — delta in units of a generic Mid 1st (`_pick_gap_equivalent`, base
  first = `elo_to_value(GENERIC_PICK_SEEDS[(1,"Mid")])`). Drives fill length.
- `gap.pick_equivalent` — nearest single generic pick `{pick_id, label, value}` or
  **null** when the gap is negligible or bigger than any one pick (then copy falls
  back to `firsts`, e.g. "≈ 1.4 mid 1sts").

`point_ratio` / `fairness` are consumed indirectly (they set `favors`/`verdict`
server-side); the bar reads `favors` + `gap` and invents no math.

## Honesty guardrails (held)

- The engine denominates the **GAP** as ONE pick-equivalent; the bar never fabricates
  a package-level pick sum ("2 firsts + a 2nd").
- Live/consensus mode shows consensus market value (basis unchanged). Mode B's
  two-board read is untouched — this only re-skins the consensus verdict card.

## Deferred (noted, not faked)

- **Per-player pick-tier chip** (tilt-bar mockup, "optional/additive"): `per_player`
  from `/api/trade/evaluate` carries only `{player_id, side, value}` — no ladder tier.
  Rendering the chip honestly needs a value→ladder-tier mapping not currently served,
  so it was left out rather than invented. Follow-up if wanted: expose the tier band
  per player from the pool seed (server) or map client-side via the #117 ladder bands.
- **Finder-card usage** (`TradeCard`): interface is built clean for it; wiring is a
  separate task per the build scope (calculator only wired here).

## Verification

- `cd mobile && npx tsc --noEmit` — clean (no errors in `TradeValueBar.tsx` /
  `ConsensusVerdictCard.tsx`; full project typecheck passes).
- Visual QA pending on-device (RN — not browser-observable).

## Docs updated

- `docs/design/components.md` → Meters & progress: added the **TradeValueBar** spec row.
