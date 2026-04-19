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
  tier: {
    elite: '#f59e0b',
    starter: '#22c55e',
    solid: '#3b82f6',
    depth: '#f97316',
    bench: '#94a3b8',
  },
} as const;

export type Position = 'QB' | 'RB' | 'WR' | 'TE';
export type Tier = 'elite' | 'starter' | 'solid' | 'depth' | 'bench';

export function tierColor(t: Tier) {
  return colors.tier[t];
}
export function posColor(p: Position) {
  return colors.position[p.toLowerCase() as keyof typeof colors.position];
}
