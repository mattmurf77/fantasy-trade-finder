# FB-213 — "Find a trade" should be present on any create-a-trade feature

- **Type:** bug (severity per operator) · **Status:** fixed 2026-08-01
  (branch `teardown-remediation` worktree)
- **Surface:** the manual calculator (`TradeCalculatorScreen`) — the
  In-league (`InLeagueCalculator`), Real values (live), and Demo modes.

## Placement chosen (and why)

ONE quiet text-link row — `Want ideas instead? Find a trade →` — rendered
directly under the calculator's mode tabs, right-aligned, chalk-dim
text-link tier (the "More ways to rank" header-link precedent; never a
button, so the calculator's own actions keep primacy).

Why this over the alternatives:

- **One affordance covers every surface.** The row sits OUTSIDE the mode
  branch, so In-league, live, and demo all carry exactly one entry —
  `InLeagueCalculator` is only ever mounted inside this screen (verified),
  so no second mount was needed and no per-mode chrome was added.
- **Not empty-state-only.** The empty state alternative hides the path the
  moment a user adds an asset; the operator's ask is discoverability from
  the create-a-trade feature, which includes mid-build.
- **Least-noisy always-visible spot.** A single 18px right-aligned text
  line under the tabs; no card, no border, no icon-button.

## Navigation

`navigation.navigate('TradesHome')` — the Trades stack's home route: the
Trade-Finding Hub with `trades.finder_hub` on (current config), the
classic Trades deck with it off. The calculator lives in the same stack,
so the navigate lands correctly from both a subnav entry and a hub launch.

## testID

`calc.find-a-trade` (registered in `mobile/src/components/CLAUDE.md`).

## Files

- `mobile/src/screens/TradeCalculatorScreen.tsx`
- `mobile/src/components/CLAUDE.md` (testID registry)

## Verification

`cd mobile && npx tsc --noEmit` clean.
