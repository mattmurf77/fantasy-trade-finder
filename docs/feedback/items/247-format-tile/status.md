# #247 — Header format tile

**Report (2026-08-05, screen TradesHome):** "Next to league in the header we
should list the format type in a brightly colored tile (so cyan)."

**Status: built (2026-08-05, branch teardown-remediation).**

## What shipped

`TopBar.tsx` (the #223 global header): the active-league cluster's name row
now carries a solid-ice tile with the league's scoring format, between the
truncating league name and the switcher chevron. testID `topbar.format`.

- **Data source:** `useSession.activeFormat` — the per-league detected
  scoring format (with the in-session SF/1QB toggle override), i.e. the same
  value every format-aware surface reads. The data model has exactly two
  formats (`shared/types.ts ScoringFormat`): `1qb_ppr` and `sf_tep` — TE
  premium is baked into the SF format, so the tile labels are **1QB** and
  **SF TEP** (compressed from the app-wide "1QB PPR" / "SF TEP" FormatToggle
  labels; PPR implied at tile size).
- **Chalkline:** solid ice fill (`ice.base`) + `ice.on` text — ice is
  correct here (the cluster is the switcher affordance / league identity);
  `radii.xs`, 11px `dataSemi` text (type floor). No new colors, no pill
  radius violation.
- **A11y:** the cluster Pressable swallows child text on iOS (documented RN
  caveat), so the format is appended to the cluster's `accessibilityLabel`
  ("League: <name>, SF TEP format").
- Renders only when a league is active AND a format is known (null until
  session bootstrap resolves; account-only sessions show the wordmark, no
  tile).

## Verification

- `cd mobile && npx tsc --noEmit` clean.
- testID `topbar.format` registered in `mobile/src/components/CLAUDE.md`.
