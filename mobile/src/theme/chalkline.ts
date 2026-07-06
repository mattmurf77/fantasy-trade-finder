// Chalkline design tokens — React Native mirror of docs/design/design-system.md.
// Status: reference implementation. Existing screens still use colors.ts/spacing.ts;
// migrate screen-by-screen by swapping imports to this module (ADR-004).
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
  lineStrong: '#3D4654', // interactive borders
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
