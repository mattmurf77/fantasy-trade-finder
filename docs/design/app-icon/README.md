# App icon master

`fleeced-app-icon-1024.png` is the square, full-bleed App Store and app icon master for Fleeced (the D-155 ram). It is 1024×1024 RGB PNG with no alpha channel, sRGB (the source's embedded ICC profile is kept), and no rounding. Apple applies the corner mask itself.

**Source:** `mobile/assets/icon.png` at `712dcbed`. Its content was introduced in `242a3995` (the D-155 ram), and it is byte-identical to the native `AppIcon.appiconset/App-Icon-1024x1024@1x.png`. No unmasked generation source is tracked.

**What changed:** the source had white rounded corners baked in. Each corner is a circular arc tangent to both edges, with a fitted r of 176.0-177.3 px (fit RMS ≤ 0.10 px). Its anti-aliased fringe runs from about 2.5 px inside the arc (a faint light rim plus a dark ringing ring) to about 1 px outside it. In each corner quadrant, every pixel whose centre lies beyond r − 3.5 px from the arc centre (the fringe plus a 1 px margin) was set to a flat fill of (24,19,26). That colour is the median of the field sampled just inside the corners and along all four edges: 23,347 of 23,348 samples are within ±4 per channel, so the brief's flat-fill rule applied rather than edge extension. 30,076 pixels changed, all inside four boxes: TL x0-176 y0-175, TR x848-1023 y0-175, BL x0-176 y847-1023, BR x848-1023 y848-1023.

**What did not change:** all 1,018,355 pixels outside the four corner zones are byte-identical to the source. The artwork, horns, eyes and field are untouched: no regeneration, recolouring, sharpening or resampling.

**Checks (2026-10-23):**
- `sips`: 1024 × 1024, `hasAlpha: no`, RGB, sRGB.
- All four corner pixels plus (40,40) and its mirrors are (24,19,26).
- Near-white pixels (all channels > 200) in each 220×220 corner box: 0 (the source had about 6,530 per box).
- A pixel diff against the source shows changes only inside the corner zones.
- Visual check at 1:1, under an iOS-style squircle mask, at 120×120, and with a 5× contrast stretch: no seam, halo or light fringe.

**Build status:** the build still uses `mobile/assets/icon.png` (the Expo `icon` and the `expo-notifications` plugin icon in `mobile/app.json`) and the native `App-Icon-1024x1024@1x.png`. Swapping either for this master is head-eng's call, and this folder does not touch them.
