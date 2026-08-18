# mobile/assets/

Four PNGs, all referenced by `../app.json`. Nothing else belongs here — in-app icons are vector, drawn by [`../src/components/chalkline/Icon.tsx`](../src/components/chalkline/Icon.tsx), and the mascot art is `react-native-svg` in [`../src/components/analyst/`](../src/components/analyst/CLAUDE.md).

| File | Referenced by | Notes |
|---|---|---|
| `icon.png` | `expo.icon` **and** the `expo-notifications` plugin's `icon` | Doubles as the push-notification icon (plugin `color` is `#56D9EC`, Chalkline ice) |
| `adaptive-icon.png` | `expo.android.adaptiveIcon.foregroundImage` | Background `#0C0E11` (Chalkline ink-0) |
| `splash-icon.png` | `expo.splash.image` | `resizeMode: contain`, background `#0C0E11` |
| `favicon.png` | `expo.web.favicon` | Web build only |

Replacing one is not enough on its own: this is a **bare workflow** (`ios/` and `android/` are checked in), so the native projects carry their own copies — `ios/DTFDynastyTradeFinder/Images.xcassets/` and `android/app/src/main/res/mipmap-*`. Update the source PNG here, then re-run `expo prebuild` (or edit the asset catalogs) and rebuild.

Brand direction: [`docs/design/brand.md`](../../docs/design/brand.md) + [`docs/design/design-system.md`](../../docs/design/design-system.md). Icon masters live under `docs/design/brand/` and explorations under `docs/design/icon-explorations/` — both are gitignored/unmerged, so they may be absent in a fresh clone.
