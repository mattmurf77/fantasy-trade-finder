# FB-192 — replace the misleading pink ranked-dots with R/NR badges

- **Type:** polish (operator-filed) · **Status:** built 2026-07-25 (branch `teardown-remediation` worktree)
- **Screen:** `InLeagueCalculator` (Calculator → In-league mode) partner chips

## What was misleading

The partner chips carried a bare 6px **flare dot** rendered only when
`has_rankings` was false — an unlabeled color signal (ADR-005 flare =
informational highlight, but a dot encodes nothing readable), and
`has_rankings` was **format-blind** while the verdict math is format-scoped,
so the dot could say "ranked" while the verdict fell back to consensus
(FB-191's confusion).

## Replacement — RankedBadge (three states)

Chalkline `Badge` construction (1px colored border + colored text on ink,
radius `--r-xs`, 11px label type), driven by coverage's new per-member
`ranked_formats` against the calculator's ACTIVE format:

| Badge | Meaning | Color |
|---|---|---|
| `R` | ranked in the active calculator format | `--pos` |
| `R*` | ranked only in the other format — board derived via FB-191 value mapping (the `*` marks derivation) | `--pos` |
| `NR` | never ranked | chalk-dim |

The third state was added because FB-191's derivation makes it a real,
user-meaningful condition — it maps 1:1 onto the response's
`opponent_board_derived` and costs one extra branch, so it doesn't
overcomplicate. Old servers without `ranked_formats` degrade to the
format-blind R/NR pair off `has_rankings`.

Accessibility: each chip's `accessibilityLabel` spells it out —
"@user, ranked" / "@user, ranked in another format, values converted" /
"@user, not ranked".

The note line under the picker follows the same three states ("Priced by your
rankings and @X's." / "@X ranked in SF TEP — values converted to 1QB PPR for
this read." / the existing hasn't-ranked invite copy), and the verdict card
adds a conversion caption when `opponent_board_derived` is set.

## Files

- `mobile/src/components/InLeagueCalculator.tsx` (`rankStateFor`, badge render, notes; flare-dot style removed)
- `docs/design/components.md` (RankedBadge spec row)
- Backend contract: `ranked_formats` on `/api/league/coverage` — see FB-191's status doc + `test_coverage_reports_ranked_formats`
