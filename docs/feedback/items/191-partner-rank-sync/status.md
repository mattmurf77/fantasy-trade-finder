# FB-191 — partner shown as "hasn't ranked" though he has (+ auto-sync)

- **Type:** bug + feature (operator-filed) · **Status:** built 2026-07-25 (branch `teardown-remediation` worktree)
- **Flag:** `rankings.cross_format_derive` (default false; `config/features.json` ships it **true**)

## Root cause

`/api/trade/evaluate` Mode B loads both boards via
`load_member_rankings(league_id, scoring_format=fmt)` — strictly
format-scoped. jonbonjourvi's rankings were published under `sf_tep`, but the
in-league calculator **hard-coded its format to `1qb_ppr`** (FB-166's gap), so
the read asked for a format he'd never saved → `opp_elo` empty → `basis:
"consensus"` → the "@jon hasn't ranked" headline. Two independent fixes ship:

1. The calculator now defaults to the league's detected format (FB-166 fix) —
   the operator's league is SF, so jon's SF board loads directly.
2. Cross-format **auto-sync** below, so even a deliberate 1QB read of an
   SF-only ranker gets his real preferences, honestly labeled.

## Auto-sync rules (the decision, pressure-tested)

**READ-TIME derivation, never a materialized copy.**

1. **Explicit-over-derived.** Derivation fires only when the member has ZERO
   `member_rankings` rows in the requested format. Real rows always win — the
   moment a user ranks format B directly, the derived board silently retires.
   No clobbering is possible because nothing is ever written.
2. **Read-time.** The derived board is recomputed per read from the source
   format's CURRENT snapshot. User updates format A → derived B follows
   immediately; there is no stale copy to invalidate. (A materialized copy
   fails both pressure tests: it goes stale when A changes and needs
   tombstoning when B gets ranked directly. Rejected.)
3. **Value-mapped, not label-copied.** Same math as
   `/api/tiers/copy-from-format` (#124): per position, keep the member's rank
   ORDER, deal out the TARGET format's consensus seed Elos to those ranks
   (`_derive_board_from_format` in `backend/server.py` — a stateless twin of
   `RankingService.apply_value_map`). An SF "worth 4 firsts" QB correctly
   reads ≈2 firsts in 1QB.
4. **Labeled, never silent.** Mode B responses add
   `{opponent_board_derived, opponent_board_derived_from, your_board_derived,
   your_board_derived_from}` (additive — old clients ignore them). The
   calculator shows "@X ranked in SF TEP — values converted" + the R* badge
   (FB-192); the verdict card carries a conversion line. `basis` becomes
   `divergence` and `opponent_has_rankings: true` — the member HAS ranked,
   which is precisely the operator's complaint.
5. **Applies to both sides.** The caller's board derives under the same rules
   (symmetric read), labeled via `your_board_derived*`.
6. **Scope: least-magic.** Derivation is wired only where the operator's case
   lives — `/api/trade/evaluate` Mode B. Trade GENERATION, matches, and
   community aggregates still read explicit rows only (deriving there changes
   engine economics — deliberate non-goal; revisit as its own item if wanted).

When to sync vs not (pressure-test summary): sync for two-sided *reads* where
"unranked" is a lie (calculator verdicts); don't sync for *writes* or for
surfaces that publish/aggregate boards (member_rankings stays
explicit-only), and never persist a derivation.

## Supporting change — coverage tells formats apart

`get_ranking_coverage` (backend/database.py) now returns per-member
`ranked_formats` (additive; legacy NULL rows count as `1qb_ppr`), so clients
can distinguish R / R* / NR (FB-192). `has_rankings` stays the format-blind
boolean for old clients.

## Tests

`backend/tests/test_cross_format_derive.py`:
- `test_derive_preserves_source_order_with_target_magnitudes`
- `test_derive_is_per_position_and_skips_unknown_pids`
- `test_opponent_ranked_only_in_other_format_is_derived_not_unranked` (the operator's case)
- `test_explicit_rankings_win_over_derivation`
- `test_caller_board_derives_too`
- `test_never_ranked_anywhere_stays_consensus`
- `test_flag_off_keeps_consensus_fallback`
- `test_coverage_reports_ranked_formats`

## Files

- `backend/server.py` (`_derive_board_from_format`, `_OTHER_FORMAT`, Mode B wiring)
- `backend/database.py` (`get_ranking_coverage.ranked_formats`)
- `backend/feature_flags.py` + `config/features.json` (`rankings.cross_format_derive`)
- `mobile/src/api/calc.ts`, `mobile/src/api/league.ts` (additive types)
- `mobile/src/components/InLeagueCalculator.tsx` (labels — see FB-192)
- `docs/api-reference.md`, `docs/config-reference.md`
