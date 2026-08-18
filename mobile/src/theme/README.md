# mobile/src/theme/

Design tokens. Three files, and the distinction between them is load-bearing — see [CLAUDE.md](CLAUDE.md).

| File | What it is |
|---|---|
| `chalkline.ts` | **THE token source** (Chalkline, ADR-004/005). Ink/chalk/ice/flare/semantic colors, `space`, `radii`, `fonts`, `type`, `maxFontScale`, `shadowSheet`, `duration`, `scrim`, `DRAG_ACTIVATION_DISTANCE`. Import from here in all new code |
| `colors.ts` | **Data-encoding hexes only** — position colors, the 8-tier pick-value ladder (#117), and the medal hues. These are cross-client contracts, not chrome |
| `spacing.ts` | Legacy 4-point scale, numerically identical to chalkline's `space`. Kept for un-migrated call sites; prefer `chalkline.ts` |

## Chrome vs. data

A **chrome** color describes the app's surface — background, border, text, the ice accent. It lives in `chalkline.ts` and can change with the design system.

A **data-encoding** color *means* something — QB red, a tier band, a medal. It lives in `colors.ts`, must match the web app and the browser extension byte-for-byte, and is governed by [docs/cross-client-invariants.md](../../../docs/cross-client-invariants.md). Changing one is a cross-client change, not a design tweak.

The old chrome palette in `colors.ts` (bg/surface/border/text/muted/accent) was deleted in the S2 teardown cleanup. Do not re-add it.

## Design system

Specs: [docs/design/design-system.md](../../../docs/design/design-system.md) + [docs/design/components.md](../../../docs/design/components.md). Live reference: [web/style-guide.html](../../../web/style-guide.html). Primitives that consume these tokens: [`../components/chalkline/`](../components/chalkline/CLAUDE.md).

Hard NEVERs (enforced by review): emoji as icons · gradients · glassmorphism/blur · Inter/Roboto/system font stacks · radius >8px except specced pills · accents other than ice (actions) and flare (informational highlights only) · ice in more than 3 places per screen · data numbers in anything but Plex Mono tabular.

Fonts load via `@expo-google-fonts/*` in `App.tsx` (Barlow Condensed, Archivo, IBM Plex Mono); components degrade to platform fonts until they settle, and a font error never blocks boot.

## Guard

```bash
npm run test:contrast    # asserts the WCAG contrast floors the design system commits to
```

It parses hexes straight out of `chalkline.ts` — a token edit that drops a committed pair below its floor fails the check.
