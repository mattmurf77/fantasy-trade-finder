// Mirrors the web app's dark theme palette (web/css/styles.css :root).
// Keeping these identical so the mobile app visually matches the site.

export const colors = {
  bg: '#0f1117',
  surface: '#1a1d27',
  border: '#2a2d3a',
  text: '#e8eaf0',
  muted: '#7a7f96',
  accent: '#4f7cff',
  green: '#22c55e',
  red: '#ef4444',
  gold: '#f59e0b',
  silver: '#94a3b8',
  bronze: '#b45309',
  position: {
    qb: '#f97316',
    rb: '#22c55e',
    wr: '#3b82f6',
    te: '#a855f7',
  },
  // Tier hues deliberately share no hue with position colors (docs/cross-client-invariants.md).
  // 8-tier pick-value ladder (2026-07-12, #117): keys read directly in draft-pick terms.
  tier: {
    firsts_4plus: '#f87171',
    firsts_3: '#e879f9',
    firsts_2: '#fbbf24',
    first_1: '#2dd4bf',
    second: '#38bdf8',
    third: '#f472b6',
    fourth: '#a3e635',
    waivers: '#7a7f96',
  },
} as const;

export type Position = 'QB' | 'RB' | 'WR' | 'TE';
export type Tier =
  | 'firsts_4plus'
  | 'firsts_3'
  | 'firsts_2'
  | 'first_1'
  | 'second'
  | 'third'
  | 'fourth'
  | 'waivers';

export function tierColor(t: Tier) {
  return colors.tier[t];
}
export function posColor(p: Position) {
  return colors.position[p.toLowerCase() as keyof typeof colors.position];
}
