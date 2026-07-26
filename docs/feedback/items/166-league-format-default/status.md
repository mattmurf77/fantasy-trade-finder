# FB-166 + FB-167 — ranking format should default to league settings

- **Covers:** feedback #166 ("This should default to your league's settings, eg superflex") and #167 ("Would also default to SFTEP. No one plays 1QB.")
- **Status:** investigated + fixed 2026-07-25 (branch `teardown-remediation` worktree)

## Findings — where the default already worked

The ranking board surfaces (Tiers, QuickSetTiers, QuickRank, ManualRanks,
Trios, PickAnchor) all read `useSession.activeFormat`, which IS
league-driven end to end (shipped as FB-80/#89):

- Backend `session_init` resolves the active format as body >
  session carry-over > **league default** (`get_league_scoring`, auto-detected
  from Sleeper `roster_positions` SUPER_FLEX / `bonus_rec_te`).
- `useLeagueFormatDefault` (mounted once in RootNav) re-applies the selected
  league's detected format on every league change, unless the user explicitly
  toggled this session (`formatExplicit`).

No change needed on those screens — they were already SF-defaulting for SF
leagues.

## The gap that WAS hard-coded (fixed)

**`InLeagueCalculator`** (Calculator → In-league mode) initialized its format
chips with `useState<ScoringFormat>('1qb_ppr')` — a hard-coded 1QB PPR default
regardless of the league. For an SF league this both showed the wrong default
AND asked the backend for 1QB boards (the FB-191 trigger: an SF-ranked partner
read as "hasn't ranked").

Fix: the calculator's format now resolves as
`local chip override ?? session activeFormat (league-detected) ?? '1qb_ppr'`.
The user can still switch via the chips; the override is calculator-local so
it never stomps the app-wide format.

## Screens changed

- `mobile/src/components/InLeagueCalculator.tsx` — league-default format (the
  only owned surface with a hard-coded default).

## Noted, not touched (outside this item's ownership)

- `mobile/src/screens/TradeCalculatorScreen.tsx` line ~103 hard-codes
  `'1qb_ppr'` for the standalone Live/Demo calculator modes — same class of
  gap, owned by the Trades-surface owner. Flagged for follow-up.
