// Chalkline design tokens — React Native mirror of docs/design/design-system.md.
// Status: live token source. The screen migration (ADR-004) is complete — all
// UI imports THIS module. colors.ts survives only as the data-encoding source
// (position/tier/medal hexes, re-exported below); spacing.ts's legacy
// radius/fontSize scales are gone. Do not add new imports of the legacy files.
//
// Fonts: install once with
//   npx expo install @expo-google-fonts/barlow-condensed @expo-google-fonts/archivo @expo-google-fonts/ibm-plex-mono expo-font
// then load in App.tsx:
//   import { useFonts } from 'expo-font';
//   import { BarlowCondensed_600SemiBold, BarlowCondensed_700Bold } from '@expo-google-fonts/barlow-condensed';
//   import { Archivo_400Regular, Archivo_500Medium, Archivo_600SemiBold, Archivo_700Bold } from '@expo-google-fonts/archivo';
//   import { IBMPlexMono_500Medium, IBMPlexMono_600SemiBold } from '@expo-google-fonts/ibm-plex-mono';
// Until fonts load, RN falls back to the platform font — layout tokens still apply.

import type { TextStyle } from 'react-native';
import { colors } from './colors';

// Palette v2 ("ice/flare", ADR-005): graphite ink + ice-cyan primary +
// flare-pink secondary. Replaced v1's turf ink + volt lime after operator
// color review (web/color-lab-2.html, option B1).
export const ink = {
  ink0: '#0C0E11', // screen background
  ink1: '#13161B', // cards, panels
  ink2: '#1A1E25', // sheets, menus, input fill
  ink3: '#232833', // pressed, wells
  line: '#262C35', // hairlines, default borders
  lineStrong: '#3D4654', // interactive borders (legacy value — 2.03:1 on ink-0)
  // Contrast-raised interactive border (teardown S2 PRD-04): ≥3:1 non-text
  // contrast — 3.25:1 on ink-0, 3.05:1 on ink-1 (2.81:1 on ink-2, where the
  // input FILL also separates the control). Components pick this over
  // lineStrong when the `visual.chalkline_cleanup` flag is on; at flag
  // cleanup it becomes the only lineStrong value.
  lineStrongA11y: '#59647A',
} as const;

export const chalk = {
  base: '#ECEFF4', // primary text
  dim: '#97A1AE', // secondary text, labels
  faint: '#626C79', // disabled, placeholders
} as const;

export const ice = {
  base: '#56D9EC', // primary CTA, active, focus, tick — ration to ≤3 per screen
  press: '#3FC2D6',
  on: '#071013', // text/icons on ice fill
} as const;

// Secondary accent — informational highlights ONLY (likes-you pill, rookie
// badge, streaks, unread markers, count emphasis). Never on actions.
export const flare = {
  base: '#F0508C',
  press: '#D8437B',
  on: '#170610',
} as const;

export const semantic = {
  pos: '#22C55E', // like/accept, positive deltas
  neg: '#EF4444', // pass/decline, errors
  warn: '#F59E0B', // warnings, injury Q
} as const;

// Position + tier hexes are cross-client invariants (docs/cross-client-invariants.md).
// Single source stays colors.ts; re-exported here so Chalkline components import one module.
export const position = colors.position;
export const tier = colors.tier;

export const space = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 48,
} as const;

// Chalkline radii are deliberately sharper than the legacy spacing.ts radius scale.
export const radii = {
  xs: 2, // badges, chips, ticks
  sm: 4, // buttons, inputs
  md: 8, // cards, sheets
  pill: 999, // count badges, likes-you pill only
} as const;

export const fonts = {
  displaySemi: 'BarlowCondensed_600SemiBold',
  displayBold: 'BarlowCondensed_700Bold',
  ui: 'Archivo_400Regular',
  uiMedium: 'Archivo_500Medium',
  uiSemi: 'Archivo_600SemiBold',
  uiBold: 'Archivo_700Bold',
  data: 'IBMPlexMono_500Medium',
  dataSemi: 'IBMPlexMono_600SemiBold',
} as const;

// Type scale — mirror of the web tokens. Data styles always tabular.
export const type = {
  display: {
    fontFamily: fonts.displayBold,
    fontSize: 32,
    lineHeight: 34,
    letterSpacing: 0.64,
    textTransform: 'uppercase',
    color: chalk.base,
  },
  heading: {
    fontFamily: fonts.displaySemi,
    fontSize: 22,
    lineHeight: 26,
    letterSpacing: 0.66,
    textTransform: 'uppercase',
    color: chalk.base,
  },
  label: {
    fontFamily: fonts.uiSemi,
    fontSize: 11,
    lineHeight: 14,
    letterSpacing: 0.88,
    textTransform: 'uppercase',
    color: chalk.dim,
  },
  title: {
    fontFamily: fonts.uiSemi,
    fontSize: 16,
    lineHeight: 22,
    color: chalk.base,
  },
  body: {
    fontFamily: fonts.ui,
    fontSize: 14,
    lineHeight: 21,
    color: chalk.base,
  },
  bodySm: {
    fontFamily: fonts.ui,
    fontSize: 13,
    lineHeight: 18,
    color: chalk.dim,
  },
  dataLg: {
    fontFamily: fonts.dataSemi,
    fontSize: 22,
    lineHeight: 26,
    fontVariant: ['tabular-nums'],
    color: chalk.base,
  },
  data: {
    fontFamily: fonts.data,
    fontSize: 13,
    lineHeight: 18,
    fontVariant: ['tabular-nums'],
    color: chalk.base,
  },
} as const satisfies Record<string, TextStyle>;

// ── Dynamic Type caps (teardown S2 PRD-01, flag `a11y.text_scaling`) ────────
// Per-style `maxFontSizeMultiplier` tiers applied by the chalkline Text
// primitive (components/chalkline/Text.tsx) when the flag is on. Flag off =
// RN default (unlimited OS scaling) — today's behavior, unchanged.
//   body    2.0  — reading copy + control labels (WCAG 1.4.4 needs ≥200%)
//   dense   1.35 — data numerals, micro-labels, fixed-pitch rows (60px tiles)
//   display 1.2  — decorative display/heading + hero numbers
export const maxFontScale = {
  body: 2.0,
  dense: 1.35,
  display: 1.2,
} as const;

// Default cap tier for each `type` style above.
export const typeMaxFontScale: Record<keyof typeof type, keyof typeof maxFontScale> = {
  display: 'display',
  heading: 'display',
  label: 'dense',
  title: 'body',
  body: 'body',
  bodySm: 'body',
  dataLg: 'display',
  data: 'dense',
};

// One shadow, sheets/menus/toasts only. Everything else: surface step + hairline.
export const shadowSheet = {
  shadowColor: '#000',
  shadowOffset: { width: 0, height: 12 },
  shadowOpacity: 0.55,
  shadowRadius: 32,
  elevation: 16,
} as const;

export const duration = {
  fast: 120,
  base: 180,
  sheet: 260,
} as const;

// Solid scrim — no blur (prohibition #3).
export const scrim = 'rgba(7,9,12,0.78)';

// Drag-to-reorder activation distance (px) for DraggableFlatList boards.
// 18 is the value Tiers landed on after the scroll-steal bug (#57); ManualRanks
// ships 5 today — the same bug. Teardown S3 PRD-04: both boards (and any
// future drag list) must pass THIS constant as `activationDistance` so
// vertical scrolling never initiates a drag. Screen wiring is wave-2 work.
export const DRAG_ACTIVATION_DISTANCE = 18;
