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

export const ink = {
  ink0: '#0D0F0B', // screen background
  ink1: '#151812', // cards, panels
  ink2: '#1D211A', // sheets, menus, input fill
  ink3: '#262B22', // pressed, wells
  line: '#31382C', // hairlines, default borders
  lineStrong: '#49523F', // interactive borders
} as const;

export const chalk = {
  base: '#EFEDE3', // primary text
  dim: '#A3A896', // secondary text, labels
  faint: '#6C7261', // disabled, placeholders
} as const;

export const volt = {
  base: '#D6F14E', // primary CTA, active, focus, tick — ration to ≤3 per screen
  press: '#BFD93F',
  on: '#12140D', // text/icons on volt fill
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
export const scrim = 'rgba(9,10,8,0.78)';
