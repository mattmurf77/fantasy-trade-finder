# mobile/src/theme/

Design tokens.

- `colors.ts` — palette including tier colors (pick-value ladder: 2+ 1sts / 1st / 2nd / 3rd / 4th / Bench). Must match the canonical hex values in `docs/cross-client-invariants.md` § Tier color tokens (shared with web + extension).
- `spacing.ts` — spacing scale.

Always reference tokens — never hard-code colors or px values in components.
