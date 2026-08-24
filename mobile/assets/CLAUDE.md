# mobile/assets/

Static image assets referenced by `../app.json`: `icon.png`, `adaptive-icon.png`, `splash-icon.png`, `favicon.png`. File-by-file map: [README.md](README.md).

## Rules

- **Only app-shell imagery.** In-app icons are vector (`components/chalkline/Icon`) and mascot art is `react-native-svg` (`components/analyst/`). Do not add raster UI assets here — the Chalkline design system has no bitmap-icon path.
- **One scoped raster exception: the mascot's pose sprites** ([D-155](../../living-memory/DECISIONS.md), 2026-08-22). If the approved mascot art is painted rather than flat, its six poses may ship as raster sprites — `@2x`/`@3x` PNG with alpha, trimmed to the pose box, target ≤ 60 KB each — and **only** under `mascot/ram/`. Nothing else in this folder or anywhere else in the app gains a bitmap path: not icons, not chrome, not badges, not backgrounds. The exception is dead until that folder exists; if the flat-vector exploration wins, it stays unused.
  - The mascot's own "no gradient, no glow" exemption is **inside its own box only** — the sprite may glow, the surface behind it may not. No halo bleeding onto ink-1 cards.
- **Bare workflow: a PNG swap is a two-step change.** `ios/` and `android/` are checked in and hold their own copies (`ios/DTFDynastyTradeFinder/Images.xcassets/`, `android/app/src/main/res/mipmap-*`). Update the source here, then re-run `expo prebuild` or edit the asset catalogs, then rebuild — editing only this folder ships the old icon.
- **`icon.png` is dual-purpose**: it is both the app icon and the `expo-notifications` plugin's notification icon. A change affects the notification shade too.
- **Background colors are tokens, not choices.** Splash and adaptive-icon backgrounds are `#0C0E11` (Chalkline ink-0); the notification tint is `#56D9EC` (ice). If `theme/chalkline.ts` moves, these move with it.
- The app's display name is set in `app.json → expo.name` **and** `ios/DTFDynastyTradeFinder/Info.plist → CFBundleDisplayName` — both, in a bare workflow (D-057).

Brand direction: [`docs/design/brand.md`](../../docs/design/brand.md) + [`docs/design/design-system.md`](../../docs/design/design-system.md). Icon masters live under `docs/design/brand/` and explorations under `docs/design/icon-explorations/` — both are gitignored/unmerged, so they may be absent in a fresh clone.
