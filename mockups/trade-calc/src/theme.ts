// Mirrors the FTF dark palette (mobile/src/theme) so the mockup reads as the same brand.

export const colors = {
  bg: '#0f1117',
  surface: '#1a1d27',
  surfaceRaised: '#222633',
  border: '#2a2d3a',
  text: '#e8eaf0',
  muted: '#7a7f96',
  accent: '#4f7cff',
  green: '#22c55e',
  red: '#ef4444',
  gold: '#f59e0b',
  position: {
    QB: '#f97316',
    RB: '#22c55e',
    WR: '#3b82f6',
    TE: '#a855f7',
  },
} as const;

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 } as const;
export const radius = { sm: 6, md: 10, lg: 14, xl: 20, pill: 999 } as const;
export const fontSize = { xs: 11, sm: 13, base: 15, lg: 18, xl: 22, xxl: 28 } as const;
