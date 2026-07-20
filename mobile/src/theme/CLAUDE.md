# mobile/src/theme/

Design tokens.

- `chalkline.ts` — THE token source (Chalkline, ADR-004/005): ink/chalk/ice/flare/semantic colors, `space`, `radii`, `fonts`, `type`, `maxFontScale` (+ `typeMaxFontScale`) Dynamic-Type caps, `shadowSheet`, `duration`, `scrim`, `DRAG_ACTIVATION_DISTANCE`. Also re-exports the position/tier data hexes.
- `colors.ts` — DATA-ENCODING hexes only since the S2 teardown cleanup: position + tier (8-tier pick-value ladder, #117 — must match `docs/cross-client-invariants.md` § Tier color tokens, shared with web + extension) and the medal hues (gold/silver/bronze, documented in `docs/design/design-system.md` → Medal). The old chrome palette (bg/surface/border/text/muted/accent) is gone — don't re-add it.
- `spacing.ts` — legacy 4-point spacing scale (numerically identical to chalkline `space`); its `radius`/`fontSize` scales are deleted. Prefer chalkline imports in new code.

Always reference tokens — never hard-code colors or px values in components.
